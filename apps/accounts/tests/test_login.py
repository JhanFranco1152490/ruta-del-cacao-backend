import hashlib
import hmac
import logging
from datetime import timedelta

import pytest
from axes.models import AccessAttempt
from django.conf import settings
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone
from rest_framework.throttling import BaseThrottle

from apps.accounts.axes import lockout_identifier
from apps.accounts.models import AuthenticationEvent
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import (
    LOGIN_URL,
    RESET_REQUEST_URL,
    login_by_document,
    login_by_email,
    reset_password,
)
from apps.accounts.throttles import LoginRateThrottle

pytestmark = pytest.mark.django_db

WRONG_PASSWORD = "contraseña equivocada"
PROXY_ADDRESS = "10.0.0.1"
CLIENT_ADDRESS = "203.0.113.5"


def through_proxy(spoofed_hop):
    """Cabeceras de un cliente que antepone una IP inventada a la que el proxy vio."""
    return {
        "REMOTE_ADDR": PROXY_ADDRESS,
        "HTTP_X_FORWARDED_FOR": f"{spoofed_hop}, {CLIENT_ADDRESS}",
    }


def with_proxies(count):
    return override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": count})


def test_login_by_email_records_success_and_last_login(api_client):
    user = UserFactory()

    response = login_by_email(api_client, user.email)

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.last_login is not None
    assert AuthenticationEvent.objects.filter(
        user=user, event_type=AuthenticationEvent.EventType.LOGIN_SUCCEEDED
    ).exists()


def test_login_by_email_ignores_case(api_client):
    UserFactory(email="ana.gomez@example.com")

    assert login_by_email(api_client, "Ana.Gomez@Example.COM").status_code == 200


def test_login_by_document_normalizes_separators(api_client):
    UserFactory(identity_document="1090123456")

    assert login_by_document(api_client, "1.090-123 456").status_code == 200


def test_nit_login_accepts_the_normalized_number(api_client):
    UserFactory(document_type="NIT", identity_document="9001234567")

    assert login_by_document(api_client, "900.123.456-7", document_type="NIT").status_code == 200


@pytest.mark.parametrize("document_type", ["CC", "CE", "PPT", "NIT"])
def test_document_must_be_digits_up_to_fifteen(api_client, document_type):
    too_long = login_by_document(api_client, "1" * 16, document_type=document_type)
    letters = login_by_document(api_client, "12345A", document_type=document_type)

    assert too_long.status_code == letters.status_code == 400
    assert "identity_document" in too_long.data["fields"]


def test_invalid_credentials_share_the_same_answer(api_client):
    user = UserFactory()

    wrong_password = login_by_email(api_client, user.email, password=WRONG_PASSWORD)
    unknown_email = login_by_email(api_client, "nadie@example.com")
    unknown_document = login_by_document(api_client, "55555555")

    assert wrong_password.status_code == 401
    assert wrong_password.data["code"] == "invalid_credentials"
    assert wrong_password.data == unknown_email.data == unknown_document.data


def test_inactive_account_with_correct_password_is_told_so(api_client):
    user = UserFactory(is_active=False)

    response = login_by_email(api_client, user.email)

    assert response.status_code == 403
    assert response.data["code"] == "account_inactive"


def test_inactive_account_with_wrong_password_reveals_nothing(api_client):
    user = UserFactory(is_active=False)

    response = login_by_email(api_client, user.email, password=WRONG_PASSWORD)

    assert response.status_code == 401
    assert response.data["code"] == "invalid_credentials"


def test_fifth_failure_locks_the_account_for_fifteen_minutes(api_client):
    user = UserFactory()
    for _ in range(4):
        assert login_by_email(api_client, user.email, password=WRONG_PASSWORD).status_code == 401

    fifth = login_by_email(api_client, user.email, password=WRONG_PASSWORD)
    with_correct_password = login_by_email(api_client, user.email)

    assert fifth.status_code == 403
    assert fifth.data["code"] == "account_locked"
    assert with_correct_password.data["code"] == "account_locked"
    assert AuthenticationEvent.objects.filter(
        event_type=AuthenticationEvent.EventType.ACCOUNT_LOCKED
    ).exists()

    AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))
    assert login_by_email(api_client, user.email).status_code == 200


def test_lockout_never_stores_the_email(api_client):
    user = UserFactory()

    login_by_email(api_client, user.email, password=WRONG_PASSWORD)

    stored = AccessAttempt.objects.get()
    assert user.email not in stored.username


def test_unknown_document_also_counts_toward_lockout(api_client):
    for _ in range(4):
        login_by_document(api_client, "55555555", password=WRONG_PASSWORD)

    assert login_by_document(api_client, "55555555", password=WRONG_PASSWORD).status_code == 403


def test_successful_login_resets_the_failure_count(api_client):
    user = UserFactory()
    for _ in range(4):
        login_by_email(api_client, user.email, password=WRONG_PASSWORD)
    assert login_by_email(api_client, user.email).status_code == 200

    for _ in range(4):
        response = login_by_email(api_client, user.email, password=WRONG_PASSWORD)

    assert response.status_code == 401


def test_lockout_is_per_user_and_ip(api_client):
    user = UserFactory()
    for _ in range(5):
        login_by_email(api_client, user.email, password=WRONG_PASSWORD, REMOTE_ADDR="10.0.0.1")

    other_ip = login_by_email(api_client, user.email, REMOTE_ADDR="10.0.0.2")

    assert other_ip.status_code == 200


def test_password_reset_clears_the_lockout(api_client):
    user = UserFactory()
    for _ in range(5):
        login_by_email(api_client, user.email, password=WRONG_PASSWORD)
    new_password = "una nueva frase segura 2026"

    reset_password(api_client, user.email, new_password)

    assert login_by_email(api_client, user.email, password=new_password).status_code == 200


def test_login_attempts_do_not_consume_the_password_reset_quota(api_client):
    user = UserFactory()
    for _ in range(6):
        login_by_email(api_client, user.email)

    response = api_client.post(RESET_REQUEST_URL, {"email": user.email}, format="json")

    assert response.status_code == 202


def test_login_requires_csrf(anonymous_client):
    user = UserFactory()

    assert login_by_email(anonymous_client, user.email).status_code == 403


def test_lockout_never_stores_form_fields_in_the_clear(api_client):
    UserFactory(email="ana.gomez@example.com")

    api_client.post(
        LOGIN_URL,
        {"login_method": "email", "email": "ana.gomez@example.com", "password": WRONG_PASSWORD},
        format="multipart",
    )
    api_client.post(
        LOGIN_URL,
        {
            "login_method": "document",
            "document_type": "CC",
            "identity_document": "77.777.777",
            "password": WRONG_PASSWORD,
        },
        format="multipart",
    )

    stored = "\n".join(AccessAttempt.objects.values_list("post_data", flat=True))
    assert AccessAttempt.objects.count() == 2
    assert "ana.gomez@example.com" not in stored
    assert "77.777.777" not in stored
    assert WRONG_PASSWORD not in stored


def test_lockout_identifier_is_a_keyed_hash():
    identifier = lockout_identifier(None, {"username": " Ana.Gomez@Example.com "})

    assert identifier == lockout_identifier(None, {"username": "ana.gomez@example.com"})
    assert identifier != hashlib.sha256(b"ana.gomez@example.com").hexdigest()
    with override_settings(SECRET_KEY="otra-llave-solo-para-pruebas"):
        assert lockout_identifier(None, {"username": "ana.gomez@example.com"}) != identifier


def test_forged_forwarded_header_is_ignored_without_trusted_proxies(api_client):
    user = UserFactory()
    for index in range(5):
        response = login_by_email(
            api_client,
            user.email,
            password=WRONG_PASSWORD,
            REMOTE_ADDR=PROXY_ADDRESS,
            HTTP_X_FORWARDED_FOR=f"198.51.100.{index}",
        )

    assert response.status_code == 403
    assert response.data["code"] == "account_locked"


@with_proxies(1)
def test_only_the_trusted_proxy_hop_decides_the_locked_address(api_client):
    user = UserFactory()
    for index in range(5):
        response = login_by_email(
            api_client, user.email, password=WRONG_PASSWORD, **through_proxy(f"198.51.100.{index}")
        )

    other_client = login_by_email(
        api_client,
        user.email,
        REMOTE_ADDR=PROXY_ADDRESS,
        HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.9",
    )
    honest_single_entry = login_by_email(
        api_client, user.email, REMOTE_ADDR=PROXY_ADDRESS, HTTP_X_FORWARDED_FOR="203.0.113.10"
    )

    assert response.status_code == 403
    assert response.data["code"] == "account_locked"
    assert other_client.status_code == 200
    assert honest_single_entry.status_code == 200


@pytest.mark.parametrize("proxies", [0, 1])
def test_axes_stores_the_same_address_the_throttles_see(api_client, proxies):
    user = UserFactory()
    headers = through_proxy("198.51.100.1")
    request = RequestFactory().post(LOGIN_URL, **headers)

    with with_proxies(proxies):
        expected = BaseThrottle().get_ident(request)
        login_by_email(api_client, user.email, password=WRONG_PASSWORD, **headers)

    assert AccessAttempt.objects.get().ip_address == expected
    assert expected == (CLIENT_ADDRESS if proxies else PROXY_ADDRESS)


def test_failed_attempt_during_the_lockout_does_not_extend_it(api_client):
    user = UserFactory()
    for _ in range(5):
        login_by_email(api_client, user.email, password=WRONG_PASSWORD)
    fourteen_minutes_ago = timezone.now() - timedelta(minutes=14)
    AccessAttempt.objects.update(attempt_time=fourteen_minutes_ago)

    during_lockout = login_by_email(api_client, user.email, password=WRONG_PASSWORD)

    assert during_lockout.data["code"] == "account_locked"
    assert AccessAttempt.objects.get().attempt_time == fourteen_minutes_ago
    AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))
    assert login_by_email(api_client, user.email).status_code == 200


def test_email_variants_and_document_share_one_lockout(api_client):
    user = UserFactory(email="ana.gomez@example.com", identity_document="1090123456")
    attempts = [
        lambda: login_by_email(api_client, "ana.gomez@example.com", password=WRONG_PASSWORD),
        lambda: login_by_email(api_client, "ANA.GOMEZ@Example.COM", password=WRONG_PASSWORD),
        lambda: login_by_email(api_client, "  Ana.Gomez@Example.com ", password=WRONG_PASSWORD),
        lambda: login_by_document(api_client, "1090123456", password=WRONG_PASSWORD),
        lambda: login_by_document(api_client, "1.090.123.456", password=WRONG_PASSWORD),
    ]
    for attempt in attempts:
        response = attempt()

    correct_password_attempts = [
        login_by_email(api_client, user.email),
        login_by_email(api_client, "ANA.GOMEZ@Example.COM"),
        login_by_document(api_client, "1090123456"),
    ]

    assert response.data["code"] == "account_locked"
    assert AccessAttempt.objects.count() == 1
    assert [r.data["code"] for r in correct_password_attempts] == ["account_locked"] * 3


# El formulario de acceso del admin usa estáticos con manifiesto, que no existen en las pruebas.
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
def test_admin_and_api_share_the_lockout_counter(api_client):
    user = UserFactory()
    admin_client = Client()
    for _ in range(5):
        admin_client.post("/admin/login/", {"username": user.email, "password": WRONG_PASSWORD})

    response = login_by_email(api_client, user.email)

    assert response.status_code == 403
    assert response.data["code"] == "account_locked"


@with_proxies(1)
@pytest.mark.parametrize("last_hop", ["garbage", "203.0.113.5:4711", "[2001:db8::1]:443", ""])
def test_unusable_trusted_hop_neither_breaks_login_nor_skips_the_lockout(api_client, last_hop):
    user = UserFactory()
    headers = {"REMOTE_ADDR": PROXY_ADDRESS, "HTTP_X_FORWARDED_FOR": f"198.51.100.1, {last_hop}"}

    for _ in range(5):
        response = login_by_email(api_client, user.email, password=WRONG_PASSWORD, **headers)

    assert response.status_code == 403
    assert response.data["code"] == "account_locked"


@with_proxies(1)
def test_login_quota_ignores_the_port_a_proxy_appends(api_client):
    def post_from_port(port):
        forwarded = f"{CLIENT_ADDRESS}:{port}"
        return api_client.post(
            LOGIN_URL, {}, format="json", REMOTE_ADDR=PROXY_ADDRESS, HTTP_X_FORWARDED_FOR=forwarded
        )

    for port in range(LoginRateThrottle().num_requests):
        assert post_from_port(port).status_code == 400

    assert post_from_port(9999).status_code == 429


def test_lockout_identifier_is_not_the_plain_hmac_of_the_secret_key():
    # SECRET_KEY firma otras cosas (sesiones, enlaces de recuperación): el identificador debe
    # derivar su propia llave para no coincidir con otro uso de la misma.
    plain = hmac.new(settings.SECRET_KEY.encode(), b"ana.gomez@example.com", hashlib.sha256)

    assert lockout_identifier(None, {"username": "ana.gomez@example.com"}) != plain.hexdigest()


def test_lockout_logs_carry_no_email_ip_or_user_agent(api_client, caplog):
    user = UserFactory()
    client_data = {"REMOTE_ADDR": "203.0.113.77", "HTTP_USER_AGENT": "NavegadorDePrueba/1.0"}

    with caplog.at_level(logging.DEBUG):
        login_by_email(api_client, user.email, password=WRONG_PASSWORD, **client_data)
        login_by_email(api_client, user.email, password=WRONG_PASSWORD, **client_data)
        login_by_email(api_client, user.email, **client_data)

    assert any(record.name.startswith("axes") for record in caplog.records)
    assert user.email not in caplog.text
    assert "203.0.113.77" not in caplog.text
    assert "NavegadorDePrueba" not in caplog.text


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"login_method": "email", "document_type": "CC", "identity_document": "12345678"},
            "El modo correo requiere únicamente email.",
        ),
        (
            {"login_method": "email", "email": "ana@example.com", "identity_document": "123"},
            "El modo correo requiere únicamente email.",
        ),
        (
            {"login_method": "document", "document_type": "CC", "email": "ana@example.com"},
            "El modo documento requiere tipo y número.",
        ),
        (
            {
                "login_method": "document",
                "document_type": "CC",
                "identity_document": "12345678",
                "email": "ana@example.com",
            },
            "El modo documento requiere tipo y número.",
        ),
    ],
)
def test_fields_of_the_other_login_method_are_rejected(api_client, payload, message):
    response = api_client.post(LOGIN_URL, {**payload, "password": WRONG_PASSWORD}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["detail"] == message
    assert AccessAttempt.objects.count() == 0
