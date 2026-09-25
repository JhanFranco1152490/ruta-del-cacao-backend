import logging
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.common.validators import strip_document_separators

from .emails import send_password_reset_email
from .exceptions import InvalidResetToken
from .models import AuthenticationEvent, RefreshSession, User

logger = logging.getLogger(__name__)

LOCKOUT_MINUTES = (3, 6, 12, 24, 48, 60)
DUMMY_PASSWORD_HASH = make_password("timing-only-password-value")


class InvalidCredentialsError(Exception):
    pass


class InactiveAccountError(Exception):
    pass


@dataclass
class AccountLockedError(Exception):
    retry_after: int


def record_authentication_event(event_type, outcome, request_id, user=None):
    AuthenticationEvent.objects.create(
        event_type=event_type,
        outcome=outcome,
        request_id=request_id,
        user=user,
    )


def authenticate_user(
    login_method, password, request_id, *, email=None, document_type=None, identity_document=None
):
    if login_method == "email":
        query = Q(email__iexact=(email or "").strip())
    else:
        query = Q(
            document_type=document_type,
            identity_document=strip_document_separators(identity_document or ""),
        )
    error = None

    with transaction.atomic():
        user = User.objects.select_for_update().filter(query).first()

        if user is None:
            check_password(password, DUMMY_PASSWORD_HASH)
            record_authentication_event(
                AuthenticationEvent.EventType.LOGIN_FAILED,
                AuthenticationEvent.Outcome.FAILURE,
                request_id,
            )
            error = InvalidCredentialsError()
        else:
            now = timezone.now()
            if user.locked_until and user.locked_until > now:
                retry_after = max(1, int((user.locked_until - now).total_seconds()))
                error = AccountLockedError(retry_after)
            elif not user.is_active:
                record_authentication_event(
                    AuthenticationEvent.EventType.LOGIN_FAILED,
                    AuthenticationEvent.Outcome.FAILURE,
                    request_id,
                    user,
                )
                error = InactiveAccountError()
            elif not user.check_password(password):
                error = _register_failed_attempt(user, request_id, now)
            else:
                _register_successful_login(user, request_id, now)
                return user

    raise error


def _register_failed_attempt(user, request_id, now):
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= 5:
        user.failed_login_attempts = 0
        user.lockout_level = min(user.lockout_level + 1, len(LOCKOUT_MINUTES))
        user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES[user.lockout_level - 1])
        user.save(update_fields=["failed_login_attempts", "lockout_level", "locked_until"])
        record_authentication_event(
            AuthenticationEvent.EventType.ACCOUNT_LOCKED,
            AuthenticationEvent.Outcome.FAILURE,
            request_id,
            user,
        )
        return AccountLockedError(LOCKOUT_MINUTES[user.lockout_level - 1] * 60)

    user.save(update_fields=["failed_login_attempts"])
    record_authentication_event(
        AuthenticationEvent.EventType.LOGIN_FAILED,
        AuthenticationEvent.Outcome.FAILURE,
        request_id,
        user,
    )
    return InvalidCredentialsError()


def _register_successful_login(user, request_id, now):
    user.failed_login_attempts = 0
    user.lockout_level = 0
    user.locked_until = None
    user.last_login = now
    user.save(
        update_fields=[
            "failed_login_attempts",
            "lockout_level",
            "locked_until",
            "last_login",
        ]
    )
    record_authentication_event(
        AuthenticationEvent.EventType.LOGIN_SUCCEEDED,
        AuthenticationEvent.Outcome.SUCCESS,
        request_id,
        user,
    )


def serialize_user(user):
    roles = list(user.groups.order_by("name").values_list("name", flat=True))
    permissions = sorted(user.get_all_permissions())
    return {
        "id": str(user.pk),
        "email": user.email,
        "roles": roles,
        "permissions": permissions,
    }


def cookie_options():
    return {
        "secure": settings.AUTH_COOKIE_SECURE,
        "httponly": True,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }


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
def confirm_password_reset(user, new_password: str, request_id) -> None:
    user.set_password(new_password)
    user.failed_login_attempts = 0
    user.lockout_level = 0
    user.locked_until = None
    user.save(update_fields=["password", "failed_login_attempts", "lockout_level", "locked_until"])
    RefreshSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    record_authentication_event(
        AuthenticationEvent.EventType.PASSWORD_RESET,
        AuthenticationEvent.Outcome.SUCCESS,
        request_id,
        user,
    )
