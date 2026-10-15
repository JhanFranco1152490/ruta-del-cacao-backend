import pytest

from apps.accounts import registry
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, PRODUCER, get_system_role

pytestmark = pytest.mark.django_db

LOT_PERMISSIONS = ["lots.view_lot", "lots.add_lot", "lots.delete_lot"]


def codes_of(role_code):
    return set(get_system_role(role_code).permission_codes)


@pytest.mark.parametrize("code", LOT_PERMISSIONS)
def test_every_lot_permission_is_delegable_and_is_a_field_permission(code):
    assert registry.is_delegable(code)
    assert registry.is_field_permission(code)
    assert registry.area_of(code) == "lots"


def test_the_producer_has_the_three_permissions():
    assert set(LOT_PERMISSIONS) <= codes_of(PRODUCER)


def test_the_foreman_views_and_creates_lots_but_does_not_delete_them():
    assert {"lots.view_lot", "lots.add_lot"} <= codes_of(FOREMAN)
    assert "lots.delete_lot" not in codes_of(FOREMAN)


def test_the_association_administrator_has_no_lot_permission():
    assert not {code for code in codes_of(ADMINISTRATOR) if code.startswith("lots.")}


def test_viewing_lots_brings_the_permission_to_see_harvests_and_their_plot():
    assert registry.with_dependencies({"lots.view_lot"}) == {
        "lots.view_lot",
        "harvests.view_harvest",
        "plots.view_plot",
        "farms.view_farm",
    }


def test_creating_and_deleting_need_to_see_lots():
    for code in ("lots.add_lot", "lots.delete_lot"):
        assert registry.PERMISSION_DEPENDENCIES[code] == "lots.view_lot"
