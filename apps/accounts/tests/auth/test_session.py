from datetime import timedelta

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.auth.services import revoke_all_sessions
from apps.accounts.models import AuthenticationEvent
from apps.accounts.system_roles import FOREMAN, PRODUCER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import (
    LOGIN_URL,
    confirm_reset,
    login_by_email,
    open_session,
    request_reset_link,
    reset_password,
)
from apps.accounts.tests.role_helpers import grant_role
from apps.accounts.throttles import LoginRateThrottle
from apps.producers.tests.factories import ProducerFactory

REFRESH_URL = "/api/auth/refresh"
LOGOUT_URL = "/api/auth/logout"
SESSION_REVOKED = AuthenticationEvent.EventType.SESSION_REVOKED
NEW_PASSWORD = "una nueva frase segura 2026"

pytestmark = pytest.mark.django_db


def test_login_sets_http_only_cookies_with_their_paths(api_client):
    user = UserFactory()
    user.groups.add(get_system_role(FOREMAN).group)

    response = login_by_email(api_client, user.email)

    assert response.status_code == 200
    assert {role["code"] for role in response.data["user"]["roles"]} == {FOREMAN}
    access, refresh = response.cookies["cacao_access"], response.cookies["cacao_refresh"]
    assert access["httponly"] and refresh["httponly"]
    assert access["path"] == "/api/"
    assert refresh["path"] == "/api/auth/"
    assert access["samesite"] == refresh["samesite"] == settings.AUTH_COOKIE_SAMESITE
    assert access["max-age"] == 15 * 60
    assert refresh["max-age"] == 7 * 24 * 60 * 60


@pytest.mark.parametrize("secure", [True, False])
def test_login_cookies_are_secure_only_when_configured(api_client, secure):
    with override_settings(AUTH_COOKIE_SECURE=secure):
        response = login_by_email(api_client, UserFactory().email)

    assert bool(response.cookies["cacao_access"]["secure"]) is secure
    assert bool(response.cookies["cacao_refresh"]["secure"]) is secure


def test_login_records_a_success_event(api_client):
    user = UserFactory()

    login_by_email(api_client, user.email)

    assert AuthenticationEvent.objects.filter(
        event_type=AuthenticationEvent.EventType.LOGIN_SUCCEEDED, user=user
    ).exists()


def test_me_returns_the_session_identity(auth_client):
    user = UserFactory()

    response = auth_client(user).get("/api/auth/me")

    assert response.status_code == 200
    assert response.data["user"]["email"] == user.email
    assert response.data["user"]["roles"] == []
    assert response.data["user"]["producer_id"] is None


def test_me_returns_roles_as_objects_and_the_producer_id(auth_client):
    producer = ProducerFactory()
    owner = grant_role(UserFactory(producer=producer), get_system_role(PRODUCER))

    response = auth_client(owner).get("/api/auth/me")

    assert response.status_code == 200
    assert response.data["user"]["roles"] == [
        {"id": str(get_system_role(PRODUCER).id), "code": PRODUCER, "name": "Productor"}
    ]
    assert str(response.data["user"]["producer_id"]) == str(producer.id)


def test_me_for_a_superuser_has_no_roles(auth_client):
    superuser = UserFactory(is_superuser=True)

    response = auth_client(superuser).get("/api/auth/me")

    assert response.status_code == 200
    assert response.data["user"]["roles"] == []
    assert "accounts.roles_manage" in response.data["user"]["permissions"]


def test_me_without_session_is_not_authenticated(api_client):
    response = api_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"


def test_expired_access_cookie_is_authentication_failed(api_client):
    token = AccessToken.for_user(UserFactory())
    token.set_exp(lifetime=-timedelta(minutes=1))
    api_client.cookies["cacao_access"] = str(token)

    response = api_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.data["code"] == "authentication_failed"


def test_garbage_access_cookie_does_not_block_login(api_client):
    api_client.cookies["cacao_access"] = "no-es-un-jwt"

    assert login_by_email(api_client, UserFactory().email).status_code == 200


def test_refresh_rotates_and_rejects_replay(auth_client):
    client = auth_client(UserFactory())
    original_refresh = client.cookies["cacao_refresh"].value

    response = client.post("/api/auth/refresh")

    assert response.status_code == 204
    assert client.cookies["cacao_refresh"].value != original_refresh
    client.cookies["cacao_refresh"] = original_refresh
    replay = client.post("/api/auth/refresh")
    assert replay.status_code == 401
    assert replay.data["code"] == "authentication_failed"
    assert replay.cookies["cacao_refresh"].value == ""


def test_refresh_without_cookie_is_rejected(api_client):
    assert api_client.post("/api/auth/refresh").status_code == 401


@pytest.mark.parametrize("change", ["delete", "deactivate"])
def test_refresh_for_deleted_or_inactive_user_is_rejected(auth_client, change):
    user = UserFactory()
    client = auth_client(user)
    if change == "delete":
        user.delete()
    else:
        user.is_active = False
        user.save(update_fields=["is_active"])

    response = client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.cookies["cacao_access"].value == ""


def test_logout_revokes_refresh_and_clears_cookies(auth_client):
    user = UserFactory()
    client = auth_client(user)
    refresh = client.cookies["cacao_refresh"].value

    response = client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert response.cookies["cacao_access"].value == ""
    assert response.cookies["cacao_refresh"].value == ""
    assert AuthenticationEvent.objects.filter(event_type=SESSION_REVOKED, user=user).count() == 1
    client.cookies["cacao_refresh"] = refresh
    assert client.post(REFRESH_URL).status_code == 401


def test_logout_works_without_the_access_cookie(api_client):
    refresh = open_session(api_client, UserFactory()).cookies["cacao_refresh"].value
    del api_client.cookies["cacao_access"]

    response = api_client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert response.cookies["cacao_access"].value == ""
    assert response.cookies["cacao_refresh"].value == ""
    api_client.cookies["cacao_refresh"] = refresh
    assert api_client.post(REFRESH_URL).status_code == 401


def test_logout_without_cookies_is_idempotent(api_client):
    response = api_client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert response.cookies["cacao_refresh"].value == ""
    assert not AuthenticationEvent.objects.filter(event_type=SESSION_REVOKED).exists()


def test_logout_with_garbage_refresh_clears_cookies_without_event(api_client):
    api_client.cookies["cacao_refresh"] = "no-es-un-jwt"

    response = api_client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert response.cookies["cacao_access"].value == ""
    assert response.cookies["cacao_refresh"].value == ""
    assert not AuthenticationEvent.objects.filter(event_type=SESSION_REVOKED).exists()


def test_repeated_logout_records_a_single_event(auth_client):
    client = auth_client(UserFactory())
    refresh = client.cookies["cacao_refresh"].value

    client.post(LOGOUT_URL)
    client.cookies["cacao_refresh"] = refresh
    assert client.post(LOGOUT_URL).status_code == 204

    assert AuthenticationEvent.objects.filter(event_type=SESSION_REVOKED).count() == 1


def test_mutation_with_session_requires_csrf(anonymous_client):
    open_session(anonymous_client, UserFactory())

    response = anonymous_client.post(LOGOUT_URL)

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_password_reset_ends_every_session_immediately(auth_client):
    user = UserFactory()
    client = auth_client(user)
    other_device = open_session(APIClient(), user)

    reset_password(client, user.email, NEW_PASSWORD)

    assert other_device.get("/api/auth/me").status_code == 401
    assert client.post(REFRESH_URL).status_code == 401


def test_password_reset_revokes_a_rotated_refresh(auth_client):
    user = UserFactory()
    client = auth_client(user)
    client.post(REFRESH_URL)
    rotated_refresh = client.cookies["cacao_refresh"].value

    reset_password(client, user.email, NEW_PASSWORD)

    client.cookies["cacao_refresh"] = rotated_refresh
    assert client.post(REFRESH_URL).status_code == 401


def test_revoking_every_session_skips_expired_tokens_in_constant_queries(
    django_assert_max_num_queries,
):
    user = UserFactory()
    live_tokens = [RefreshToken.for_user(user) for _ in range(3)]
    expired_token = RefreshToken.for_user(user)
    OutstandingToken.objects.filter(jti=expired_token["jti"]).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    BlacklistedToken.objects.create(token=OutstandingToken.objects.get(jti=live_tokens[0]["jti"]))

    with django_assert_max_num_queries(2):
        revoke_all_sessions(user)

    revoked = set(BlacklistedToken.objects.values_list("token__jti", flat=True))
    assert revoked == {token["jti"] for token in live_tokens}


def test_logging_in_invalidates_a_pending_reset_link(api_client):
    user = UserFactory()
    uid, token = request_reset_link(api_client, user.email)

    login_by_email(api_client, user.email)
    response = confirm_reset(api_client, uid, token, NEW_PASSWORD)

    assert response.status_code == 400
    assert response.data["code"] == "invalid_reset_token"


def test_csrf_rejected_posts_do_not_spend_the_login_quota(api_client):
    limit = LoginRateThrottle().num_requests
    cross_site = APIClient(enforce_csrf_checks=True)

    for _ in range(limit + 5):
        assert cross_site.post(LOGIN_URL, {}, format="json").status_code == 403

    assert login_by_email(api_client, UserFactory().email).status_code == 200


def test_browser_flow_with_cors_and_csrf():
    user = UserFactory()
    with override_settings(
        CORS_ALLOWED_ORIGINS=["http://localhost:3000"],
        CSRF_TRUSTED_ORIGINS=["http://localhost:3000"],
    ):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf", HTTP_ORIGIN="http://localhost:3000")
        assert csrf["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert csrf["Access-Control-Allow-Credentials"] == "true"

        response = login_by_email(
            client,
            user.email,
            HTTP_ORIGIN="http://localhost:3000",
            HTTP_X_CSRFTOKEN=csrf.data["csrf_token"],
        )

        assert response.status_code == 200
        assert client.get("/api/auth/me").status_code == 200
