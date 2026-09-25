import re

from django.core import mail

from .factories import DEFAULT_PASSWORD

LOGIN_URL = "/api/auth/login"
RESET_REQUEST_URL = "/api/auth/password-reset/request"
RESET_CONFIRM_URL = "/api/auth/password-reset/confirm"


def login_by_email(client, email, password=DEFAULT_PASSWORD, **extra):
    return client.post(
        LOGIN_URL,
        {"login_method": "email", "email": email, "password": password},
        format="json",
        **extra,
    )


def reset_link_params(message) -> tuple[str, str]:
    uid = re.search(r"uid=([^&\s]+)", message.body).group(1)
    token = re.search(r"token=([^&\s]+)", message.body).group(1)
    return uid, token


def request_reset_link(client, email) -> tuple[str, str]:
    client.post(RESET_REQUEST_URL, {"email": email}, format="json")
    return reset_link_params(mail.outbox[-1])


def confirm_reset(client, uid, token, password, confirmation=None):
    return client.post(
        RESET_CONFIRM_URL,
        {
            "uid": uid,
            "token": token,
            "new_password": password,
            "new_password_confirmation": confirmation or password,
        },
        format="json",
    )


def reset_password(client, email, new_password):
    uid, token = request_reset_link(client, email)
    return confirm_reset(client, uid, token, new_password)
