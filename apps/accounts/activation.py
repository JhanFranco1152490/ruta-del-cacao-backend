import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes, force_str
from django.utils.http import base36_to_int, urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status

from apps.common.exceptions import ApiError

from .emails import send_activation_email
from .events import record_account_event
from .models import AccountManagementEvent, User

ACTIVATION_TOKEN_TIMEOUT = 60 * 60 * 72  # 72 horas

logger = logging.getLogger(__name__)


class InvalidActivationToken(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El enlace no es válido o ya venció. Pide que te reenvíen la activación."
    default_code = "invalid_activation_token"


class ActivationTokenGenerator(PasswordResetTokenGenerator):
    """Token de un solo uso para activar una cuenta, con su propia vigencia (72 horas).

    Hereda el hash de `PasswordResetTokenGenerator` (incluye la contraseña y el último inicio
    de sesión: deja de servir al usarlo, o si la persona inicia sesión antes por otra vía).
    `key_salt` distinto separa este token del de recuperación de contraseña: aunque se generaran
    en el mismo instante para la misma cuenta, el hash da un valor distinto y uno no sirve para
    el otro. `check_token()` se reescribe porque la clase base lee
    `settings.PASSWORD_RESET_TIMEOUT` directamente, sin una forma de sustituirlo por instancia
    ni por subclase.
    """

    key_salt = "apps.accounts.activation.ActivationTokenGenerator"

    def check_token(self, user, token):
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-")
        except ValueError:
            return False
        try:
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False

        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False

        if (self._num_seconds(self._now()) - ts) > ACTIVATION_TOKEN_TIMEOUT:
            return False
        return True


activation_token_generator = ActivationTokenGenerator()


def send_activation(user) -> bool:
    """Envía el enlace de activación. Devuelve si el correo salió, sin que la persona que creó
    la cuenta se entere de la razón exacta si falla (puede ser un dato del proveedor de correo).
    """
    query = urlencode(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": activation_token_generator.make_token(user),
        }
    )
    activation_url = f"{settings.FRONTEND_URL.rstrip('/')}/activar-cuenta?{query}"
    try:
        send_activation_email(user, activation_url, hours=ACTIVATION_TOKEN_TIMEOUT // 3600)
    except Exception as error:
        # Nunca el mensaje de la excepción: puede traer el correo del destinatario.
        logger.error(
            "No se pudo enviar el correo de activación (usuario %s, %s)",
            user.pk,
            type(error).__name__,
        )
        return False
    return True


def user_from_activation_link(uid: str, token: str) -> User:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, ValidationError):
        raise InvalidActivationToken() from None
    if not activation_token_generator.check_token(user, token):
        raise InvalidActivationToken()
    return user


@transaction.atomic
def confirm_activation(user, token: str, new_password: str, request_id) -> None:
    # El enlace ya se validó fuera de la transacción; con dos confirmaciones simultáneas ambas
    # lo darían por bueno. Bloquear la fila y volver a validar deja pasar solo a la primera: al
    # fijar la contraseña, el token de la segunda deja de servir.
    user = User.objects.select_for_update().filter(pk=user.pk, is_active=True).first()
    if user is None or not activation_token_generator.check_token(user, token):
        raise InvalidActivationToken()
    user.set_password(new_password)
    user.save(update_fields=["password"])
    record_account_event(
        AccountManagementEvent.EventType.ACCOUNT_ACTIVATED,
        request_id,
        target_user=user,
    )
