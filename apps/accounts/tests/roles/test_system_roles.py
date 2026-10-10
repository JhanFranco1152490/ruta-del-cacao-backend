from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission

from apps.accounts.apps import last_app_with_models
from apps.accounts.models import Role
from apps.accounts.registry import PERMISSION_DEPENDENCIES, is_delegable
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


FARM_MANAGEMENT = {"farms.add_farm", "farms.change_farm", "farms.delete_farm"}
# Los cuatro, incluido consultar: la asociación no ve parcelas.
PLOT_PERMISSIONS = {"plots.view_plot", "plots.add_plot", "plots.change_plot", "plots.delete_plot"}


@pytest.mark.parametrize(
    "permissions", [FARM_MANAGEMENT, PLOT_PERMISSIONS], ids=["farm_management", "plots"]
)
def test_only_the_producer_role_manages_farms_and_has_plots(permissions):
    for code, definition in SYSTEM_ROLES.items():
        granted = permissions & set(definition["permissions"])
        assert granted == (permissions if code == PRODUCER else set()), code


@pytest.mark.parametrize(
    "permission, holder",
    [
        # Caracterizar es parte de la operación de cada productor.
        ("crops.change_plotcharacterization", PRODUCER),
        # El catálogo de variedades es de toda la asociación.
        ("crops.manage_cacaovariety", ADMINISTRATOR),
    ],
)
def test_each_crops_permission_belongs_to_a_single_system_role(permission, holder):
    granted = {
        code
        for code, definition in SYSTEM_ROLES.items()
        if permission in definition["permissions"]
    }
    assert granted == {holder}


def test_only_the_producer_and_the_association_read_farms():
    readers = {
        code
        for code, definition in SYSTEM_ROLES.items()
        if "farms.view_farm" in definition["permissions"]
    }
    assert readers == {PRODUCER, ADMINISTRATOR}


def test_only_the_association_can_delete_producers():
    granted = {
        code
        for code, definition in SYSTEM_ROLES.items()
        if "producers.delete" in definition["permissions"]
    }
    assert granted == {ADMINISTRATOR}


def test_deleting_a_producer_requires_seeing_them():
    assert PERMISSION_DEPENDENCIES["producers.delete"] == "producers.view"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("accounts.users_view", True),
        ("accounts.roles_manage", True),
        ("producers.view", False),
        ("producers.delete", False),
        ("farms.view_farm", True),
        ("farms.add_farm", True),
        ("farms.change_farm", True),
        ("farms.delete_farm", True),
        ("plots.view_plot", True),
        ("plots.add_plot", True),
        ("plots.change_plot", True),
        ("plots.delete_plot", True),
        ("crops.change_plotcharacterization", True),
        ("crops.manage_cacaovariety", False),
        ("accounts.unknown_permission", False),
    ],
)
def test_is_delegable(code, expected):
    assert is_delegable(code) is expected


@pytest.mark.parametrize("code", [ADMINISTRATOR, PRODUCER])
def test_the_administrator_and_the_producer_can_delete_accounts(code):
    assert "accounts.users_delete" in get_system_role(code).permission_codes


@pytest.mark.parametrize("code", [FOREMAN, QUALITY_MANAGER, SALES_MANAGER])
def test_the_predefined_roles_cannot_delete_accounts(code):
    assert "accounts.users_delete" not in get_system_role(code).permission_codes


INPUT_VIEW = "inputs.view_agriculturalinput"
INPUT_ADD = "inputs.add_agriculturalinput"
INPUT_CHANGE = "inputs.change_agriculturalinput"
INPUT_DELETE = "inputs.delete_agriculturalinput"
INPUT_STOCK = "inputs.manage_inputstock"


def _holders(permission):
    return {
        code
        for code, definition in SYSTEM_ROLES.items()
        if permission in definition["permissions"]
    }


@pytest.mark.parametrize("permission", [INPUT_VIEW, INPUT_ADD, INPUT_CHANGE, INPUT_STOCK])
def test_the_producer_and_the_foreman_work_the_inputs_catalog(permission):
    assert _holders(permission) == {PRODUCER, FOREMAN}


def test_only_the_producer_deletes_inputs_and_can_delegate_it():
    assert _holders(INPUT_DELETE) == {PRODUCER}


@pytest.mark.parametrize(
    "permission", [INPUT_VIEW, INPUT_ADD, INPUT_CHANGE, INPUT_DELETE, INPUT_STOCK]
)
def test_the_inputs_permissions_are_delegable_and_the_association_has_none(permission):
    assert is_delegable(permission)
    assert ADMINISTRATOR not in _holders(permission)
