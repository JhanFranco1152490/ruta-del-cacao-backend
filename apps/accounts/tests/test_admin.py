import pytest
from axes.models import AccessAttempt
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.axes import lockout_identifier
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import login_by_email

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]

WRONG_PASSWORD = "contraseña equivocada"
REFRESH_URL = "/api/auth/refresh"


@pytest.fixture
def admin_client():
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


def lock_out(api_client, user):
    for _ in range(5):
        login_by_email(api_client, user.email, password=WRONG_PASSWORD)
    assert login_by_email(api_client, user.email).data["code"] == "account_locked"


def assert_can_log_in(api_client, user):
    assert login_by_email(api_client, user.email).status_code == 200


def test_no_token_blacklist_model_is_registered_in_the_admin():
    models = apps.get_app_config("token_blacklist").get_models()

    assert [model for model in models if admin.site.is_registered(model)] == []


@pytest.mark.parametrize(
    "path",
    [
        "/admin/token_blacklist/outstandingtoken/",
        "/admin/token_blacklist/outstandingtoken/{outstanding}/change/",
        "/admin/token_blacklist/blacklistedtoken/",
        "/admin/token_blacklist/blacklistedtoken/add/",
        "/admin/token_blacklist/blacklistedtoken/{blacklisted}/change/",
        "/admin/token_blacklist/blacklistedtoken/{blacklisted}/delete/",
    ],
)
def test_token_blacklist_pages_do_not_exist_even_for_a_superuser(admin_client, path):
    outstanding = OutstandingToken.objects.create(
        user=UserFactory(),
        jti="jti-de-prueba",
        token="token-de-prueba",
        expires_at="2099-01-01T00:00:00Z",
    )
    blacklisted = BlacklistedToken.objects.create(token=outstanding)

    response = admin_client.get(
        path.format(outstanding=outstanding.pk, blacklisted=blacklisted.pk)
    )

    assert response.status_code == 404


def test_a_deleted_blacklist_row_cannot_be_reached_to_revive_a_token(admin_client):
    outstanding = OutstandingToken.objects.create(
        user=UserFactory(),
        jti="jti-de-prueba",
        token="token-de-prueba",
        expires_at="2099-01-01T00:00:00Z",
    )
    blacklisted = BlacklistedToken.objects.create(token=outstanding)

    response = admin_client.post(
        f"/admin/token_blacklist/blacklistedtoken/{blacklisted.pk}/delete/", {"post": "yes"}
    )

    assert response.status_code == 404
    assert BlacklistedToken.objects.filter(pk=blacklisted.pk).exists()


def test_refresh_tokens_never_appear_in_any_admin_page(api_client, admin_client):
    user = UserFactory()
    login_by_email(api_client, user.email)
    rotated_out = api_client.cookies[settings.AUTH_REFRESH_COOKIE].value
    api_client.post(REFRESH_URL)
    current = api_client.cookies[settings.AUTH_REFRESH_COOKIE].value
    assert OutstandingToken.objects.filter(token__in=[rotated_out, current]).count() == 2
    assert BlacklistedToken.objects.count() == 1

    pages = [reverse("admin:index")]
    for model in admin.site._registry:
        opts = model._meta
        pages.append(reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist"))
        pages += [
            reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
            for obj in model._default_manager.all()[:5]
        ]

    for page in pages:
        response = admin_client.get(page)
        assert response.status_code == 200, page
        body = response.content.decode()
        assert rotated_out not in body and current not in body, page


def test_axes_reset_unlocks_a_locked_account(api_client):
    user = UserFactory()
    lock_out(api_client, user)

    call_command("axes_reset")

    assert_can_log_in(api_client, user)


def test_axes_reset_ip_unlocks_only_the_accounts_locked_from_that_address(api_client):
    user = UserFactory()
    lock_out(api_client, user)
    ip_address = AccessAttempt.objects.get().ip_address

    call_command("axes_reset_ip", "192.0.2.1")
    assert login_by_email(api_client, user.email).data["code"] == "account_locked"

    call_command("axes_reset_ip", ip_address)
    assert_can_log_in(api_client, user)


def test_axes_reset_username_needs_the_stored_hash_not_the_email(api_client):
    user = UserFactory()
    lock_out(api_client, user)

    call_command("axes_reset_username", user.email)
    assert login_by_email(api_client, user.email).data["code"] == "account_locked"

    call_command("axes_reset_username", lockout_identifier(None, {"username": user.email}))
    assert_can_log_in(api_client, user)


def test_deleting_the_access_attempt_in_the_admin_unlocks_the_account(api_client, admin_client):
    user = UserFactory()
    lock_out(api_client, user)
    attempt = AccessAttempt.objects.get()

    changelist = admin_client.get(
        reverse("admin:axes_accessattempt_changelist"), {"q": attempt.ip_address}
    )
    assert changelist.status_code == 200
    assert reverse("admin:axes_accessattempt_change", args=[attempt.pk]) in (
        changelist.content.decode()
    )

    deletion = admin_client.post(
        reverse("admin:axes_accessattempt_delete", args=[attempt.pk]), {"post": "yes"}
    )

    assert deletion.status_code == 302
    assert_can_log_in(api_client, user)
