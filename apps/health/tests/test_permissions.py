from apps.accounts import registry
from apps.accounts.system_roles import ADMINISTRATOR, SYSTEM_ROLES

MANAGE = "health.manage_pestdisease"


def test_only_the_association_manages_the_pests_catalog():
    holders = {code for code, role in SYSTEM_ROLES.items() if MANAGE in role["permissions"]}

    assert holders == {ADMINISTRATOR}


def test_managing_the_catalog_cannot_be_delegated():
    # El catálogo es de toda la asociación: un productor no se lo pasa a sus empleados.
    assert registry.is_delegable(MANAGE) is False
    assert MANAGE in registry.PERMISSION_REGISTRY


def test_managing_the_catalog_is_not_a_field_permission():
    assert not registry.is_field_permission(MANAGE)
