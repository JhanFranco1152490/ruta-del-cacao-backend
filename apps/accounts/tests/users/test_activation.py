import smtplib
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import AccountManagementEvent
from apps.accounts.tests.factories import UserFactory, make_pending_user
from apps.accounts.tests.helpers import (
    ACTIVATION_CONFIRM_URL,
    RESET_REQUEST_URL,
    confirm_activation_request,
    confirm_reset,
    request_reset_link,
    reset_link_params,
)
from apps.accounts.throttles import ActivationConfirmThrottle
from apps.accounts.users.activation import (
    ACTIVATION_TOKEN_TIMEOUT,
    activation_token_generator,
    send_activation,
)

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "una nueva frase segura 2026"


def activation_link_for(user) -> tuple[str, str]:
    send_activation(user)
    return reset_link_params(mail.outbox[-1])


@override_settings(FRONTEND_URL="https://app.example.com/")
def test_email_points_to_the_frontend_and_has_html_version():
    user = make_pending_user()

    send_activation(user)

    message = mail.outbox[0]
    assert "https://app.example.com/activar-cuenta?uid=" in message.body
    assert "&token=" in message.body
    assert "&amp;" not in message.body
    assert "72 horas" in message.body
    assert message.alternatives[0].mimetype == "text/html"
    assert "&amp;token=" in message.alternatives[0].content


def test_confirm_activates_the_account_and_records_the_event(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)

    response = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert AccountManagementEvent.objects.filter(
        target_user=user, event_type=AccountManagementEvent.EventType.ACCOUNT_ACTIVATED
    ).exists()


def test_confirm_does_not_set_session_cookies(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)

    response = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)

    assert "cacao_access" not in response.cookies
    assert "cacao_refresh" not in response.cookies


def test_link_is_single_use(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)

    first = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)
    second = confirm_activation_request(api_client, uid, token, "otra frase segura 2026")

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.data["code"] == "invalid_activation_token"


def test_link_is_still_valid_a_second_before_seventy_two_hours(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)
    still_valid = datetime.now() + timedelta(seconds=ACTIVATION_TOKEN_TIMEOUT - 1)

    with mock.patch.object(activation_token_generator, "_now", return_value=still_valid):
        response = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 204


def test_link_expires_after_seventy_two_hours_and_one_second(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)
    expired = datetime.now() + timedelta(seconds=ACTIVATION_TOKEN_TIMEOUT + 1)

    with mock.patch.object(activation_token_generator, "_now", return_value=expired):
        response = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_activation_token"


def test_token_from_another_account_is_rejected(api_client):
    user = make_pending_user()
    other = make_pending_user()
    _, token = activation_link_for(user)
    other_uid = urlsafe_base64_encode(force_bytes(other.pk))

    response = confirm_activation_request(api_client, other_uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_activation_token"


def test_changing_the_email_invalidates_a_pending_link(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)
    user.email = f"cambiado-{user.email}"
    user.save(update_fields=["email"])

    response = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_activation_token"


def test_activation_token_does_not_work_as_a_reset_token(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)

    response = confirm_reset(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_reset_token"


def test_reset_token_does_not_work_as_an_activation_token(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    response = confirm_activation_request(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_activation_token"


@pytest.mark.parametrize("uid", ["no-es-base64", "MTIz"])
def test_malformed_uid_is_an_invalid_link(api_client, uid):
    response = confirm_activation_request(api_client, uid, "token", NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_activation_token"


def test_mismatched_passwords_are_rejected(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)

    response = confirm_activation_request(
        api_client, uid, token, NEW_PASSWORD, confirmation="otra frase distinta 2026"
    )

    assert response.status_code == 400
    assert "new_password_confirmation" in response.data["fields"]


def test_weak_password_is_rejected_by_the_shared_policy(api_client):
    user = make_pending_user()
    uid, token = activation_link_for(user)

    response = confirm_activation_request(api_client, uid, token, "12345678")

    assert response.status_code == 400
    assert "new_password" in response.data["fields"]


def test_confirm_requires_csrf(anonymous_client):
    response = anonymous_client.post(ACTIVATION_CONFIRM_URL, {}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_confirm_has_its_own_request_quota(api_client):
    limit = ActivationConfirmThrottle().num_requests
    for _ in range(limit):
        confirm_activation_request(api_client, "uid", "token", NEW_PASSWORD)

    response = confirm_activation_request(api_client, "uid", "token", NEW_PASSWORD)

    assert response.status_code == 429


def test_password_reset_request_on_a_pending_account_sends_no_email(api_client):
    user = make_pending_user()

    response = api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")

    assert response.status_code == 202
    assert mail.outbox == []


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        recipients = {address: (550, b"rechazado") for m in email_messages for address in m.to}
        raise smtplib.SMTPRecipientsRefused(recipients)


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "apps.accounts.tests.test_activation.FailingEmailBackend",
            "OPTIONS": {},
        }
    }
)
def test_send_activation_returns_false_and_logs_no_email(caplog):
    user = make_pending_user()

    result = send_activation(user)

    assert result is False
    assert str(user.pk) in caplog.text
    assert user.email not in caplog.text
