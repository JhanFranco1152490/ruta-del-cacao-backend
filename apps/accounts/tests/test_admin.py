import pytest
from axes.models import AccessAttempt
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.auth.axes import lockout_identifier
from apps.accounts.models import AccountManagementEvent, Role, User
from apps.accounts.system_roles import ADMINISTRATOR
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import login_by_email
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]

WRONG_PASSWORD = "contraseña equivocada"
REFRESH_URL = "/api/auth/refresh"


@pytest.fixture
def superuser_account():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def admin_client(superuser_account):
    client = Client()
    client.force_login(superuser_account)
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


# --- Role y Group ---


def test_group_is_not_registered_in_the_admin():
    assert not admin.site.is_registered(Group)


def test_nobody_can_add_edit_or_delete_a_role_from_the_admin(admin_client):
    role = Role.objects.get(code=ADMINISTRATOR)

    assert admin_client.get(reverse("admin:accounts_role_add")).status_code == 403

    change_url = reverse("admin:accounts_role_change", args=[role.pk])
    assert admin_client.get(change_url).status_code == 200
    response = admin_client.post(change_url, {"name": "Otro nombre"})
    assert response.status_code == 403
    role.refresh_from_db()
    assert role.name == "Administrador"

    delete_url = reverse("admin:accounts_role_delete", args=[role.pk])
    assert admin_client.get(delete_url).status_code == 403


# --- User: productor y roles ---


def test_the_user_admin_shows_the_producer_and_its_roles_as_read_only(admin_client):
    owner = make_producer_owner(ProducerFactory())

    change_url = reverse("admin:accounts_user_change", args=[owner.pk])
    body = admin_client.get(change_url).content.decode()

    assert owner.producer.member_code in body
    assert "Productor" in body
    assert 'name="groups"' not in body


# --- User: las escrituras pasan por los servicios de cuentas ---


def user_form(user, **overrides):
    data = {
        "email": user.email,
        "document_type": user.document_type,
        "identity_document": user.identity_document,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": "on" if user.is_active else "",
        "is_staff": "on" if user.is_staff else "",
        "is_superuser": "on" if user.is_superuser else "",
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


def user_url(name, user):
    return reverse(f"admin:accounts_user_{name}", args=[user.pk])


def employee():
    return UserFactory(producer=ProducerFactory(), first_name="Ana", last_name="Prueba")


def issue_session(user):
    RefreshToken.for_user(user)


def sessions_revoked(user):
    return not OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).exists()


def test_an_account_cannot_be_added_from_the_admin(admin_client):
    before = User.objects.count()

    assert admin_client.get(reverse("admin:accounts_user_add")).status_code == 403
    response = admin_client.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "sinrol@example.com",
            "document_type": "CC",
            "identity_document": "99887766",
            "password1": "Clave-segura-12345",
            "password2": "Clave-segura-12345",
        },
    )

    assert response.status_code == 403
    assert User.objects.count() == before


def test_editing_the_data_goes_through_update_account_and_revokes_the_sessions_of_a_new_email(
    admin_client,
):
    user = employee()
    issue_session(user)

    response = admin_client.post(
        user_url("change", user),
        user_form(user, first_name="Ana María", email="nuevo.correo@example.com"),
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert (user.first_name, user.email) == ("Ana María", "nuevo.correo@example.com")
    assert sessions_revoked(user)


def test_a_repeated_email_is_refused_and_nothing_changes(admin_client):
    user = employee()
    other = UserFactory(producer=user.producer)
    original = user.email

    response = admin_client.post(
        user_url("change", user), user_form(user, email=other.email, first_name="Otro")
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert (user.email, user.first_name) == (original, "Ana")


def test_deactivating_goes_through_set_account_status(admin_client, superuser_account):
    user = employee()
    issue_session(user)

    admin_client.post(user_url("change", user), user_form(user, is_active=""))

    user.refresh_from_db()
    assert not user.is_active
    assert sessions_revoked(user)
    event = AccountManagementEvent.objects.get(target_user=user)
    assert event.event_type == AccountManagementEvent.EventType.ACCOUNT_DEACTIVATED
    assert event.actor == superuser_account


def test_the_last_administrator_cannot_be_deactivated_from_the_admin(admin_client):
    administrator = make_administrator()
    response = admin_client.post(
        user_url("change", administrator), user_form(administrator, is_active=""), follow=True
    )

    administrator.refresh_from_db()
    assert administrator.is_active
    assert response.redirect_chain[-1][0] == user_url("change", administrator)


def test_an_account_that_never_signed_in_is_deleted_through_the_service(
    admin_client, superuser_account
):
    user = employee()

    response = admin_client.post(user_url("delete", user), {"post": "yes"})

    assert response.status_code == 302
    assert not User.objects.filter(pk=user.pk).exists()
    event = AccountManagementEvent.objects.get(target_user_ref=user.pk)
    assert event.event_type == AccountManagementEvent.EventType.ACCOUNT_DELETED
    assert event.actor == superuser_account


def test_an_account_that_already_signed_in_is_not_deleted_and_the_admin_says_why(admin_client):
    user = employee()
    User.objects.filter(pk=user.pk).update(last_login=timezone.now())

    response = admin_client.post(user_url("delete", user), {"post": "yes"}, follow=True)

    assert User.objects.filter(pk=user.pk).exists()
    assert "inició sesión" in response.content.decode()


def test_the_bulk_delete_action_is_not_offered_for_accounts(admin_client):
    employee()

    body = admin_client.get(reverse("admin:accounts_user_changelist")).content.decode()

    assert "delete_selected" not in body


def test_the_last_login_cannot_be_edited_to_get_around_the_delete_rule(admin_client):
    user = employee()
    User.objects.filter(pk=user.pk).update(last_login=timezone.now())

    admin_client.post(
        user_url("change", user),
        {**user_form(user), "last_login_0": "", "last_login_1": ""},
    )

    user.refresh_from_db()
    assert user.last_login is not None


def test_the_personal_data_of_a_producer_account_is_read_only(admin_client):
    owner = make_producer_owner(ProducerFactory())
    original = owner.first_name

    admin_client.post(user_url("change", owner), user_form(owner, first_name="Cambiado"))

    owner.refresh_from_db()
    assert owner.first_name == original
    body = admin_client.get(user_url("change", owner)).content.decode()
    assert 'name="first_name"' not in body


def test_a_technical_account_is_edited_directly_and_cannot_be_deleted(admin_client):
    technical = UserFactory(is_staff=True, is_superuser=True, first_name="Técnica")

    admin_client.post(
        user_url("change", technical), user_form(technical, first_name="Equipo técnico")
    )

    technical.refresh_from_db()
    assert technical.first_name == "Equipo técnico"
    assert admin_client.post(user_url("delete", technical), {"post": "yes"}).status_code == 403
    assert User.objects.filter(pk=technical.pk).exists()


def test_the_technical_flags_are_saved_directly_for_a_superuser(admin_client):
    user = employee()

    admin_client.post(user_url("change", user), user_form(user, is_staff="on"))

    user.refresh_from_db()
    assert user.is_staff


def test_a_new_password_from_the_admin_revokes_the_sessions(admin_client):
    user = employee()
    issue_session(user)

    response = admin_client.post(
        reverse("admin:auth_user_password_change", args=[user.pk]),
        {"password1": "otra clave segura 2026", "password2": "otra clave segura 2026"},
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("otra clave segura 2026")
    assert sessions_revoked(user)


def test_a_rejected_password_form_leaves_the_sessions_open(admin_client):
    user = employee()
    issue_session(user)

    admin_client.post(
        reverse("admin:auth_user_password_change", args=[user.pk]),
        {"password1": "una clave", "password2": "otra distinta"},
    )

    assert not sessions_revoked(user)


def test_the_permissions_follow_the_api_ones():
    user = employee()
    viewer = Client()
    viewer.force_login(
        UserFactory(is_staff=True, producer=user.producer, permissions=["accounts.users_view"])
    )

    assert viewer.get(user_url("change", user)).status_code == 200
    assert (
        viewer.post(user_url("change", user), user_form(user, first_name="X")).status_code == 403
    )
    assert viewer.post(user_url("delete", user), {"post": "yes"}).status_code == 403


def test_staff_who_is_not_the_technical_account_only_reaches_the_accounts_it_can_manage():
    mine = employee()
    theirs = employee()
    technical = UserFactory(is_staff=True, is_superuser=True, email="tecnica@example.com")
    delegate = make_delegate(mine.producer, ["accounts.users_view", "accounts.users_update"])
    delegate.is_staff = True
    delegate.save(update_fields=["is_staff"])
    client = Client()
    client.force_login(delegate)

    body = client.get(reverse("admin:accounts_user_changelist")).content.decode()

    assert mine.email in body
    assert theirs.email not in body and technical.email not in body
    assert client.get(user_url("change", theirs)).status_code == 302
