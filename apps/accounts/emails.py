from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

SENDER_NAME = "Ruta del Cacao"


def _sender() -> str:
    """El remitente con nombre visible. Una dirección sola (`no-reply@...`) es una señal que los
    filtros de spam castigan; si `DEFAULT_FROM_EMAIL` ya trae un nombre, se respeta."""
    name, address = parseaddr(settings.DEFAULT_FROM_EMAIL)
    if name:
        return settings.DEFAULT_FROM_EMAIL
    return formataddr((SENDER_NAME, address))


def _send(user, *, subject: str, template: str, context: dict) -> None:
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"accounts/email/{template}.txt", context),
        from_email=_sender(),
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string(f"accounts/email/{template}.html", context), "text/html"
    )
    message.send()


def send_password_reset_email(user, reset_url: str) -> None:
    context = {"reset_url": reset_url, "minutes": settings.PASSWORD_RESET_TIMEOUT // 60}
    _send(user, subject="Restablece tu contraseña", template="password_reset", context=context)


def send_activation_email(user, activation_url: str, hours: int) -> None:
    context = {"activation_url": activation_url, "hours": hours}
    _send(user, subject="Activa tu cuenta", template="account_activation", context=context)
