import logging
from urllib.parse import urlencode

from axes.utils import reset as reset_axes_attempts
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .axes import lockout_identifier
from .emails import send_password_reset_email
from .exceptions import (
    AccountInactive,
    AccountLocked,
    InvalidCredentials,
    InvalidResetToken,
    SessionExpired,
)
from .models import AuthenticationEvent, User

logger = logging.getLogger(__name__)


def record_authentication_event(event_type, outcome, request_id, user=None):
    AuthenticationEvent.objects.create(
        event_type=event_type,
        outcome=outcome,
        request_id=request_id,
        user=user,
    )


def resolve_login_username(*, email=None, document_type=None, identity_document=None) -> str:
    """Devuelve el correo con el que se autentica la cuenta.

    Si el documento no existe se devuelve un identificador inventado: el intento se cuenta
    igual para el bloqueo y la respuesta no revela si la cuenta existe.
    """
    if email:
        return email.strip().lower()
    account_email = (
        User.objects.filter(document_type=document_type, identity_document=identity_document)
        .values_list("email", flat=True)
        .first()
    )
    return account_email or f"{document_type}:{identity_document}"


def log_in(request, *, username: str, password: str, request_id) -> User:
    # axes necesita el request para saber la IP del intento.
    user = authenticate(request, username=username, password=password)
    if user is None:
        locked = getattr(request, "axes_locked_out", False)
        record_authentication_event(
            (
                AuthenticationEvent.EventType.ACCOUNT_LOCKED
                if locked
                else AuthenticationEvent.EventType.LOGIN_FAILED
            ),
            AuthenticationEvent.Outcome.FAILURE,
            request_id,
            User.objects.filter(email=username).first(),
        )
        raise AccountLocked() if locked else InvalidCredentials()
    if not user.is_active:
        record_authentication_event(
            AuthenticationEvent.EventType.LOGIN_FAILED,
            AuthenticationEvent.Outcome.FAILURE,
            request_id,
            user,
        )
        raise AccountInactive()
    # La señal actualiza last_login y hace que axes reinicie el contador de fallos.
    user_logged_in.send(sender=user.__class__, request=request, user=user)
    record_authentication_event(
        AuthenticationEvent.EventType.LOGIN_SUCCEEDED,
        AuthenticationEvent.Outcome.SUCCESS,
        request_id,
        user,
    )
    return user


def clear_lockout(user) -> None:
    reset_axes_attempts(username=lockout_identifier(None, {"username": user.email}))


def issue_tokens(user) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def rotate_tokens(raw_refresh: str) -> tuple[str, str]:
    serializer = TokenRefreshSerializer(data={"refresh": raw_refresh})
    try:
        serializer.is_valid(raise_exception=True)
    except (TokenError, AuthenticationFailed, ObjectDoesNotExist, DRFValidationError):
        # Vencido, revocado, reutilizado, de un usuario inactivo o borrado: para el cliente
        # todos significan lo mismo, volver a iniciar sesión.
        raise SessionExpired() from None
    return serializer.validated_data["access"], serializer.validated_data["refresh"]


def end_session(raw_refresh: str | None, request_id) -> None:
    """Revoca la renovación si sigue vigente; si no hay nada que revocar, no hace nada."""
    if not raw_refresh:
        return
    try:
        token = RefreshToken(raw_refresh)
    except TokenError:
        return
    user = User.objects.filter(pk=token[api_settings.USER_ID_CLAIM]).first()
    token.blacklist()
    record_authentication_event(
        AuthenticationEvent.EventType.SESSION_REVOKED,
        AuthenticationEvent.Outcome.SUCCESS,
        request_id,
        user,
    )


def revoke_all_sessions(user) -> None:
    # Cada renovación deja un token nuevo y esto corre con la fila del usuario bloqueada: se
    # omiten los vencidos (ya no sirven) y los ya bloqueados, y el resto va en una sola inserción.
    # ignore_conflicts cubre el que una renovación simultánea bloquee entre la consulta y ella.
    pending = OutstandingToken.objects.filter(
        user=user, expires_at__gt=timezone.now(), blacklistedtoken__isnull=True
    )
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in pending], ignore_conflicts=True
    )


def request_password_reset(email: str) -> None:
    user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if user is None:
        return
    query = urlencode(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
    )
    reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/restablecer-contrasena?{query}"
    # Un fallo del envío no puede cambiar la respuesta: tiene que ser la misma exista o no la
    # cuenta. Tampoco se registra el mensaje de la excepción: puede traer el destinatario.
    try:
        send_password_reset_email(user, reset_url)
    except Exception as error:
        logger.error(
            "No se pudo enviar el correo de recuperación (usuario %s, %s)",
            user.pk,
            type(error).__name__,
        )


def user_from_reset_link(uid: str, token: str) -> User:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, ValidationError):
        raise InvalidResetToken() from None
    # El token incluye el hash de la contraseña y la fecha del último login: deja de servir
    # en cuanto se usa o la persona vuelve a entrar.
    if not default_token_generator.check_token(user, token):
        raise InvalidResetToken()
    return user


@transaction.atomic
def confirm_password_reset(user, token: str, new_password: str, request_id) -> None:
    # El enlace ya se validó fuera de la transacción; con dos confirmaciones simultáneas
    # ambas lo darían por bueno. Bloquear la fila y volver a validar deja pasar solo a la
    # primera: al cambiar la contraseña, el token de la segunda deja de servir.
    user = User.objects.select_for_update().filter(pk=user.pk, is_active=True).first()
    if user is None or not default_token_generator.check_token(user, token):
        raise InvalidResetToken()
    user.set_password(new_password)
    user.save(update_fields=["password"])
    revoke_all_sessions(user)
    clear_lockout(user)
    record_authentication_event(
        AuthenticationEvent.EventType.PASSWORD_RESET,
        AuthenticationEvent.Outcome.SUCCESS,
        request_id,
        user,
    )
