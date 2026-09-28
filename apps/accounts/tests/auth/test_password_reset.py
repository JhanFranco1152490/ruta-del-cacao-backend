import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest import mock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.db import connection
from django.test import override_settings

from apps.accounts.models import AuthenticationEvent
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import (
    RESET_CONFIRM_URL,
    RESET_REQUEST_URL,
    confirm_reset,
    csrf_client,
    request_reset_link,
)
from apps.accounts.throttles import PasswordResetIPThrottle

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "una nueva frase segura 2026"


def test_request_does_not_reveal_whether_the_account_exists(api_client):
    user = UserFactory()

    existing = api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")
    unknown = api_client.post(RESET_REQUEST_URL, {"email": "nadie@example.com"}, format="json")

    assert existing.status_code == unknown.status_code == 202
    assert existing.data == unknown.data
    assert len(mail.outbox) == 1


def test_mixed_case_email_receives_the_link(api_client):
    user = UserFactory(email="ana.gomez@example.com")

    api_client.post(RESET_REQUEST_URL, {"email": "Ana.Gomez@Example.COM"}, format="json")

    assert mail.outbox[0].to == [user.email]


def test_inactive_account_receives_no_email(api_client):
    user = UserFactory(is_active=False)

    api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")

    assert mail.outbox == []


@override_settings(FRONTEND_URL="https://app.example.com/")
def test_email_points_to_the_frontend_and_has_html_version(api_client):
    user = UserFactory()

    api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")

    message = mail.outbox[0]
    assert "https://app.example.com/restablecer-contrasena?uid=" in message.body
    assert "&token=" in message.body
    assert "&amp;" not in message.body
    assert "30 minutos" in message.body
    assert message.alternatives[0].mimetype == "text/html"
    assert "&amp;token=" in message.alternatives[0].content


def test_confirm_changes_password_and_records_event(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    response = confirm_reset(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert AuthenticationEvent.objects.filter(
        user=user, event_type=AuthenticationEvent.EventType.PASSWORD_RESET
    ).exists()


def test_link_is_single_use(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    first = confirm_reset(api_client, uid, token, NEW_PASSWORD)
    second = confirm_reset(api_client, uid, token, "otra frase segura 2026")

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.data["code"] == "invalid_reset_token"


def test_link_expires_after_thirty_minutes(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)
    later = datetime.now() + timedelta(minutes=31)

    with mock.patch.object(default_token_generator, "_now", return_value=later):
        response = confirm_reset(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_reset_token"


@pytest.mark.django_db(transaction=True)
def test_simultaneous_confirmations_with_the_same_link_succeed_only_once():
    user = UserFactory()
    client = csrf_client()
    uid, token = request_reset_link(client, user.email)
    attempts = [
        (client, "primera frase segura 2026"),
        (csrf_client(), "segunda frase segura 2026"),
    ]
    barrier = Barrier(len(attempts))

    def confirm(attempt):
        attempt_client, password = attempt
        try:
            barrier.wait()
            return confirm_reset(attempt_client, uid, token, password)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(attempts)) as executor:
        responses = list(executor.map(confirm, attempts))

    assert sorted(response.status_code for response in responses) == [204, 400]
    winner = next(
        password for (_, password), r in zip(attempts, responses) if r.status_code == 204
    )
    loser = next(response for response in responses if response.status_code == 400)
    assert loser.data["code"] == "invalid_reset_token"
    user.refresh_from_db()
    assert user.check_password(winner)


def test_confirm_has_its_own_request_quota(api_client):
    for index in range(PasswordResetIPThrottle().num_requests):
        api_client.post(RESET_REQUEST_URL, {"email": f"persona{index}@example.com"}, format="json")

    response = confirm_reset(api_client, "uid", "token", NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_reset_token"


@pytest.mark.parametrize("body", ["[]", '["a@example.com"]', '"texto"', "1", "null"])
def test_request_with_a_body_that_is_not_an_object_is_a_validation_error(api_client, body):
    response = api_client.post(RESET_REQUEST_URL, body, content_type="application/json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


@pytest.mark.parametrize("uid", ["no-es-base64", "MTIz"])
def test_malformed_uid_is_an_invalid_link(api_client, uid):
    response = confirm_reset(api_client, uid, "token", NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_reset_token"


def test_mismatched_passwords_are_rejected(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    response = confirm_reset(
        api_client, uid, token, NEW_PASSWORD, confirmation="otra frase distinta 2026"
    )

    assert response.status_code == 400
    assert "new_password_confirmation" in response.data["fields"]


def test_weak_password_is_rejected_by_the_policy(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    response = confirm_reset(api_client, uid, token, "12345678")

    assert response.status_code == 400
    assert "new_password" in response.data["fields"]


def test_password_resembling_the_identity_document_is_rejected(api_client):
    user = UserFactory(identity_document="1090123456")
    uid, token = request_reset_link(api_client, user.email)

    response = confirm_reset(api_client, uid, token, "cc1090123456x")

    assert response.status_code == 400
    assert "new_password" in response.data["fields"]


def test_rejects_fewer_than_eight_characters(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    response = confirm_reset(api_client, uid, token, "C@cao!7")

    assert response.status_code == 400
    assert "new_password" in response.data["fields"]
    user.refresh_from_db()
    assert not user.check_password("C@cao!7")


@pytest.mark.parametrize("password", ["C@cao!7x", "C@cao!7x" + "z" * 42])
def test_accepts_eight_and_fifty_characters(api_client, password):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    assert confirm_reset(api_client, uid, token, password).status_code == 204


def test_rejects_more_than_fifty_characters(api_client):
    response = confirm_reset(api_client, "uid", "token", "C@cao!7x" + "z" * 43)

    assert response.status_code == 400
    assert "new_password" in response.data["fields"]


def test_request_requires_csrf(anonymous_client):
    response = anonymous_client.post(RESET_REQUEST_URL, {"email": "a@example.com"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert mail.outbox == []


def test_confirm_requires_csrf(anonymous_client):
    response = anonymous_client.post(RESET_CONFIRM_URL, {}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


@override_settings(
    MAILERS={"default": {"BACKEND": "anymail.backends.test.EmailBackend", "OPTIONS": {}}}
)
def test_email_is_accepted_by_the_anymail_backend(api_client):
    user = UserFactory()

    api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")

    assert hasattr(mail.outbox[0], "anymail_test_params")


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        recipients = {address: (550, b"rechazado") for m in email_messages for address in m.to}
        raise smtplib.SMTPRecipientsRefused(recipients)


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "apps.accounts.tests.test_password_reset.FailingEmailBackend",
            "OPTIONS": {},
        }
    }
)
def test_send_failure_keeps_the_same_response_and_logs_no_email(api_client, caplog):
    user = UserFactory()

    existing = api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")
    unknown = api_client.post(RESET_REQUEST_URL, {"email": "nadie@example.com"}, format="json")

    assert existing.status_code == unknown.status_code == 202
    assert existing.data == unknown.data
    assert str(user.pk) in caplog.text
    assert user.email not in caplog.text
