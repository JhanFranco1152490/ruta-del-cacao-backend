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

EVALUATE = "quality.evaluate_lot"
CLASSIFY = "quality.classify_lot"
DISCARD = "quality.discard_lot"
QUALITY_PERMISSIONS = [EVALUATE, CLASSIFY, DISCARD]

# Ver el lote arrastra ver su cosecha, su parcela y su finca.
TO_SEE_THE_LOT = {"lots.view_lot", "harvests.view_harvest", "plots.view_plot", "farms.view_farm"}


def holders(permission):
    return {
        code
        for code, definition in SYSTEM_ROLES.items()
        if permission in definition["permissions"]
    }


@pytest.mark.parametrize("permission", QUALITY_PERMISSIONS)
def test_the_quality_permissions_are_delegable_field_permissions(permission):
    assert registry.is_delegable(permission)
    assert registry.is_field_permission(permission)
    assert registry.area_of(permission) == "quality"


def test_evaluating_brings_the_permission_to_see_the_lot():
    assert registry.with_dependencies({EVALUATE}) == {EVALUATE, *TO_SEE_THE_LOT}


@pytest.mark.parametrize("permission", [CLASSIFY, DISCARD])
def test_classifying_and_discarding_bring_evaluating(permission):
    # Quien clasifica o descarta trabaja en la pantalla de calidad, que pide evaluar.
    assert registry.with_dependencies({permission}) == {permission, EVALUATE, *TO_SEE_THE_LOT}


@pytest.mark.parametrize("permission", QUALITY_PERMISSIONS)
def test_the_producer_and_the_quality_manager_hold_the_quality_permissions(permission):
    assert holders(permission) == {PRODUCER, QUALITY_MANAGER}


def test_the_quality_manager_sees_the_lots_and_works_their_quality_only():
    assert set(SYSTEM_ROLES[QUALITY_MANAGER]["permissions"]) == {
        *QUALITY_PERMISSIONS,
        *TO_SEE_THE_LOT,
    }


@pytest.mark.parametrize("role", [ADMINISTRATOR, FOREMAN, SALES_MANAGER])
def test_the_other_roles_have_no_quality_permission(role):
    assert not {code for code in SYSTEM_ROLES[role]["permissions"] if code.startswith("quality.")}
