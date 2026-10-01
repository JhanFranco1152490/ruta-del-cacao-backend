from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission

from apps.accounts.apps import last_app_with_models
from apps.accounts.models import Role
from apps.accounts.registry import is_delegable
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    SALES_MANAGER,
    SYSTEM_ROLES,
    get_system_role,
    sync_system_roles,
)
from apps.accounts.tests.factories import RoleFactory

pytestmark = pytest.mark.django_db


def test_the_five_system_roles_exist_after_migrating():
    # No llama a sync_system_roles(): el post_migrate de la base de pruebas ya la corrió.
    codes = set(Role.objects.filter(code__isnull=False).values_list("code", flat=True))
    assert codes == {ADMINISTRATOR, PRODUCER, FOREMAN, QUALITY_MANAGER, SALES_MANAGER}


def test_roles_sync_after_the_last_app_that_has_models():
    with_models = SimpleNamespace(label="farms", models_module=object())
    without_models = SimpleNamespace(label="reports", models_module=None)

    assert last_app_with_models([with_models, without_models]) is with_models


def test_running_sync_again_makes_no_changes():
    before = list(Role.objects.order_by("code").values("id", "code", "group_id"))
    sync_system_roles()
    after = list(Role.objects.order_by("code").values("id", "code", "group_id"))
    assert before == after


def test_sync_restores_a_permission_removed_by_hand():
    role = get_system_role(ADMINISTRATOR)
    permission = Permission.objects.get(content_type__app_label="producers", codename="view")
    role.group.permissions.remove(permission)

    sync_system_roles()

    assert permission in get_system_role(ADMINISTRATOR).group.permissions.all()


def test_sync_never_touches_a_custom_role():
    custom = RoleFactory(name="Rol propio de prueba")

    sync_system_roles()

    custom.refresh_from_db()
    assert custom.kind == Role.Kind.CUSTOM


def test_each_system_role_has_exactly_its_declared_permissions():
    for code, definition in SYSTEM_ROLES.items():
        role = get_system_role(code)
        actual = {
            f"{permission.content_type.app_label}.{permission.codename}"
            for permission in role.group.permissions.all()
        }
        assert actual == set(definition["permissions"])


FARM_PERMISSIONS = {"farms.view_farm", "farms.add_farm", "farms.change_farm"}


def test_only_the_producer_role_manages_farms():
    for code, definition in SYSTEM_ROLES.items():
        granted = FARM_PERMISSIONS & set(definition["permissions"])
        assert granted == (FARM_PERMISSIONS if code == PRODUCER else set()), code


@pytest.mark.parametrize(
    "code, expected",
    [
        ("accounts.users_view", True),
        ("accounts.roles_manage", True),
        ("accounts.association_access_manage", False),
        ("producers.view", False),
        ("farms.view_farm", True),
        ("farms.add_farm", True),
        ("farms.change_farm", True),
        ("accounts.unknown_permission", False),
    ],
)
def test_is_delegable(code, expected):
    assert is_delegable(code) is expected
