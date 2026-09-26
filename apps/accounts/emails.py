from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_password_reset_email(user, reset_url: str) -> None:
    context = {"reset_url": reset_url, "minutes": settings.PASSWORD_RESET_TIMEOUT // 60}
    message = EmailMultiAlternatives(
        subject="Restablece tu contraseña",
        body=render_to_string("accounts/email/password_reset.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string("accounts/email/password_reset.html", context), "text/html"
    )
    message.send()
