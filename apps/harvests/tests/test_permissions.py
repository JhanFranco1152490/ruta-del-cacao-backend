import pytest

from apps.accounts import registry
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, PRODUCER, get_system_role
from apps.accounts.tests.role_helpers import make_delegate
from apps.accounts.users.farm_assignment import needs_farm
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

HARVEST_PERMISSIONS = [
    "harvests.view_harvest",
    "harvests.add_harvest",
    "harvests.change_harvest",
    "harvests.delete_harvest",
]


def codes_of(role_code):
    return set(get_system_role(role_code).permission_codes)


@pytest.mark.parametrize("code", HARVEST_PERMISSIONS)
def test_every_harvest_permission_is_delegable_and_is_a_field_permission(code):
    assert registry.is_delegable(code)
    assert registry.is_field_permission(code)
    assert registry.area_of(code) == "harvests"


def test_the_producer_has_the_four_permissions():
    assert set(HARVEST_PERMISSIONS) <= codes_of(PRODUCER)


def test_the_foreman_registers_and_corrects_but_does_not_delete():
    assert set(HARVEST_PERMISSIONS[:3]) <= codes_of(FOREMAN)
    assert "harvests.delete_harvest" not in codes_of(FOREMAN)


def test_the_association_roles_have_no_harvest_permission():
    assert not {c for c in codes_of(ADMINISTRATOR) if c.startswith("harvests.")}


def test_registering_brings_the_permissions_to_see_them_and_their_plot():
    assert registry.with_dependencies({"harvests.add_harvest"}) == {
        "harvests.add_harvest",
        "harvests.view_harvest",
        "plots.view_plot",
        "farms.view_farm",
    }


def test_deleting_and_correcting_need_to_see_harvests():
    for code in ("harvests.change_harvest", "harvests.delete_harvest"):
        assert registry.PERMISSION_DEPENDENCIES[code] == "harvests.view_harvest"


def test_an_employee_with_a_harvest_permission_needs_a_farm():
    producer = ProducerFactory()
    without_farm = make_delegate(producer, ["harvests.view_harvest"])
    farm = FarmFactory(producer=producer)
    with_farm = make_delegate(producer, ["harvests.view_harvest"], farm=farm)

    assert needs_farm(without_farm) is True
    assert needs_farm(with_farm) is False
