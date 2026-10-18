import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.common.tests.concurrency import run_in_parallel
from apps.facilities.exceptions import (
    DuplicateFacilityName,
    FarmInactive,
    FarmNotFound,
    FarmRequired,
)
from apps.facilities.models import PostharvestFacility, PostharvestFacilityAuditEvent
from apps.facilities.services import create_facility
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestFacilityFactory, facility_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def farm():
    return FarmFactory()


@pytest.fixture
def owner(farm):
    return make_producer_owner(farm.producer)


def test_creates_an_available_facility_in_the_farm(owner, farm):
    facility = create_facility(owner, facility_data(farm, name=" C-04 "))

    assert facility.farm_id == farm.pk
    assert (facility.name, facility.capacity_kg, facility.is_active, facility.version) == (
        "C-04",
        600,
        True,
        1,
    )
    assert facility.created_by == owner
    assert facility.has_records is False


def test_the_creation_leaves_its_event_with_every_value(owner, farm):
    facility = create_facility(owner, facility_data(farm))

    event = PostharvestFacilityAuditEvent.objects.get(facility=facility)
    assert (event.action, event.actor, event.version, event.farm_ref) == (
        "created",
        owner,
        1,
        farm.pk,
    )
    assert event.changes == {
        "capacity_kg": {"before": None, "after": "600.0"},
        "facility_type": {"before": None, "after": "fermentation_box"},
        "is_active": {"before": None, "after": True},
        "name": {"before": None, "after": "C-04"},
    }


def test_a_name_already_used_in_the_farm_is_rejected_with_the_existing_one(owner, farm):
    existing = PostharvestFacilityFactory(farm=farm, name="C-02")

    with pytest.raises(DuplicateFacilityName) as error:
        create_facility(owner, facility_data(farm, name="c 02", facility_type="solar_dryer"))

    assert error.value.extra["existing"]["id"] == str(existing.pk)
    assert PostharvestFacility.objects.count() == 1


def test_the_same_name_is_accepted_in_another_farm(owner, farm):
    PostharvestFacilityFactory(farm=farm, name="C-02")
    other = FarmFactory(producer=farm.producer)

    assert create_facility(owner, facility_data(other, name="C-02")).farm_id == other.pk


def test_an_inactive_farm_does_not_receive_facilities(owner):
    farm = FarmFactory(producer=owner.producer, is_active=False)

    with pytest.raises(FarmInactive):
        create_facility(owner, facility_data(farm))


def test_a_farm_of_another_producer_does_not_exist(owner):
    with pytest.raises(FarmNotFound):
        create_facility(owner, facility_data(FarmFactory()))


def test_an_employee_registers_only_in_its_own_farms(farm):
    other = FarmFactory(producer=farm.producer)
    employee = make_delegate(farm.producer, ["facilities.add_postharvestfacility"], farm=farm)

    assert create_facility(employee, facility_data(farm)).farm_id == farm.pk
    with pytest.raises(FarmNotFound):
        create_facility(employee, facility_data(other))


def test_the_technical_account_registers_in_any_farm(farm):
    facility = create_facility(UserFactory(is_superuser=True), facility_data(farm))

    assert facility.farm_id == farm.pk


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_creations_with_the_same_name_leave_one():
    farm = FarmFactory(producer=ProducerFactory())
    owner = make_producer_owner(farm.producer)

    def attempt(_):
        try:
            return create_facility(owner, facility_data(farm))
        except DuplicateFacilityName as error:
            return error

    results = run_in_parallel(attempt, [1, 2])

    assert sum(isinstance(result, DuplicateFacilityName) for result in results) == 1
    assert PostharvestFacility.objects.count() == 1
    assert PostharvestFacilityAuditEvent.objects.count() == 1


def test_an_employee_without_a_farm_cannot_register(farm):
    employee = make_delegate(farm.producer, ["facilities.add_postharvestfacility"])

    with pytest.raises(FarmRequired):
        create_facility(employee, facility_data(farm))
