import pytest

from apps.accounts import registry
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    SALES_MANAGER,
    SYSTEM_ROLES,
)

VIEW = "warehouse.view_stock"
ENTRY = "warehouse.register_entry"
EXIT = "warehouse.register_exit"
MANAGE = "warehouse.manage_warehouse"
WRITE_PERMISSIONS = [ENTRY, EXIT, MANAGE]
WAREHOUSE_PERMISSIONS = [VIEW, *WRITE_PERMISSIONS]


def holders(permission):
    return {
        code
        for code, definition in SYSTEM_ROLES.items()
        if permission in definition["permissions"]
    }


@pytest.mark.parametrize("permission", WAREHOUSE_PERMISSIONS)
def test_the_warehouse_permissions_are_delegable_field_permissions(permission):
    assert registry.is_delegable(permission)
    assert registry.is_field_permission(permission)
    assert registry.area_of(permission) == "warehouse"


def test_viewing_the_stock_brings_the_permission_to_see_the_farm_only():
    # Las existencias llevan el código del lote y su finca, no su cosecha ni su parcela.
    assert registry.with_dependencies({VIEW}) == {VIEW, "farms.view_farm"}


@pytest.mark.parametrize("permission", WRITE_PERMISSIONS)
def test_every_write_brings_viewing_the_stock(permission):
    assert registry.with_dependencies({permission}) == {permission, VIEW, "farms.view_farm"}


@pytest.mark.parametrize("permission", [VIEW, *WRITE_PERMISSIONS])
def test_the_producer_holds_every_warehouse_permission(permission):
    assert PRODUCER in holders(permission)


@pytest.mark.parametrize("permission", WAREHOUSE_PERMISSIONS)
def test_the_quality_manager_works_the_warehouse(permission):
    assert QUALITY_MANAGER in holders(permission)


def test_the_sales_manager_only_looks_at_the_stock_to_prepare_sales():
    held = {c for c in SYSTEM_ROLES[SALES_MANAGER]["permissions"] if c.startswith("warehouse.")}

    assert held == {VIEW}
    assert "farms.view_farm" in SYSTEM_ROLES[SALES_MANAGER]["permissions"]


@pytest.mark.parametrize("role", [ADMINISTRATOR, FOREMAN])
def test_the_association_and_the_foreman_have_no_warehouse_permission(role):
    assert not {c for c in SYSTEM_ROLES[role]["permissions"] if c.startswith("warehouse.")}


def test_the_role_permissions_close_over_their_dependencies():
    for role in (PRODUCER, QUALITY_MANAGER, SALES_MANAGER):
        permissions = set(SYSTEM_ROLES[role]["permissions"])
        assert registry.with_dependencies(permissions) == permissions, role
