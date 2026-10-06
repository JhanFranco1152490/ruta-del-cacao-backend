import pytest
from django.core import mail
from django.test import override_settings

from apps.accounts.emails import send_activation_email, send_password_reset_email
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = "https://app.example.com/activar-cuenta?uid=abc&token=def-123"

SENDERS = [
    pytest.param(lambda user: send_activation_email(user, URL, hours=72), id="activation"),
    pytest.param(lambda user: send_password_reset_email(user, URL), id="password-reset"),
]


@pytest.mark.parametrize("send", SENDERS)
@override_settings(DEFAULT_FROM_EMAIL="no-reply@example.com")
def test_the_sender_has_a_display_name_so_it_is_not_a_bare_address(send):
    send(UserFactory())

    assert mail.outbox[0].from_email == "Ruta del Cacao <no-reply@example.com>"


@pytest.mark.parametrize("send", SENDERS)
@override_settings(DEFAULT_FROM_EMAIL="Asociación <no-reply@example.com>")
def test_a_configured_display_name_is_kept(send):
    send(UserFactory())

    assert mail.outbox[0].from_email == "Asociación <no-reply@example.com>"


@pytest.mark.parametrize("send", SENDERS)
def test_both_versions_show_the_link_in_the_clear(send):
    send(UserFactory())

    message = mail.outbox[0]
    html = message.alternatives[0].content
    assert URL in message.body
    assert f">{URL.replace('&', '&amp;')}</a>" in html


@pytest.mark.parametrize("send", SENDERS)
def test_the_html_declares_its_charset_and_title(send):
    send(UserFactory())

    html = mail.outbox[0].alternatives[0].content
    assert '<meta charset="utf-8"' in html
    assert "<title>" in html
