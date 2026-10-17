import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.facilities.exceptions import (
    DuplicateFacilityName,
    FacilityFieldsLocked,
    FacilityNotFound,
    StaleFacilityVersion,
)
from apps.facilities.models import PostharvestFacilityAuditEvent
from apps.facilities.services import update_facility
from apps.farms.tests.factories import FarmFactory

from .factories import PostharvestFacilityFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def box():
    return PostharvestFacilityFactory(name="C-02", capacity_kg=600)


@pytest.fixture
def owner(box):
    return make_producer_owner(box.farm.producer)


def events(facility, action):
    return PostharvestFacilityAuditEvent.objects.filter(facility=facility, action=action)


def test_name_and_capacity_change_and_the_version_goes_up(owner, box):
    updated = update_facility(owner, box.pk, 1, {"name": " C-2 ", "capacity_kg": 650})

    assert (updated.name, updated.capacity_kg, updated.version) == ("C-2", 650, 2)
    event = events(box, "updated").get()
    assert event.changes == {
        "capacity_kg": {"before": 600, "after": 650},
        "name": {"before": "C-02", "after": "C-2"},
    }


def test_the_type_changes_while_the_facility_was_never_used(owner, box):
    updated = update_facility(owner, box.pk, 1, {"facility_type": "solar_dryer"})

    assert updated.facility_type == "solar_dryer"


def test_the_type_of_a_used_facility_is_locked(used_facility):
    owner = make_producer_owner(used_facility.farm.producer)

    with pytest.raises(FacilityFieldsLocked) as error:
        update_facility(owner, used_facility.pk, 1, {"facility_type": "solar_dryer"})

    assert "facility_type" in error.value.fields


def test_a_used_facility_still_changes_its_name_and_capacity(used_facility):
    owner = make_producer_owner(used_facility.farm.producer)

    updated = update_facility(owner, used_facility.pk, 1, {"name": "C-99", "capacity_kg": 700})

    assert (updated.name, updated.capacity_kg, updated.has_records) == ("C-99", 700, True)


def test_deactivating_and_activating_leave_a_status_event(owner, box):
    update_facility(owner, box.pk, 1, {"is_active": False})
    activated = update_facility(owner, box.pk, 2, {"is_active": True})

    assert (activated.is_active, activated.version) == (True, 3)
    assert events(box, "status_changed").count() == 2
    assert not events(box, "updated").exists()


def test_an_inactive_facility_can_be_edited(owner):
    facility = PostharvestFacilityFactory(
        farm=FarmFactory(producer=owner.producer), is_active=False
    )

    assert update_facility(owner, facility.pk, 1, {"name": "C-50"}).name == "C-50"


def test_a_repeated_name_in_the_farm_is_rejected(owner, box):
    PostharvestFacilityFactory(farm=box.farm, name="M-01", facility_type="solar_dryer")

    with pytest.raises(DuplicateFacilityName):
        update_facility(owner, box.pk, 1, {"name": "m 01"})


def test_an_inactive_facility_still_counts_for_the_repeated_name(owner, box):
    PostharvestFacilityFactory(farm=box.farm, name="C-09", is_active=False)

    with pytest.raises(DuplicateFacilityName):
        update_facility(owner, box.pk, 1, {"name": "C-09"})


def test_a_stale_version_is_rejected_with_the_current_facility(owner, box):
    update_facility(owner, box.pk, 1, {"capacity_kg": 650})

    with pytest.raises(StaleFacilityVersion) as error:
        update_facility(owner, box.pk, 1, {"capacity_kg": 700})

    assert error.value.current_facility.capacity_kg == 650


def test_a_retry_of_a_change_already_applied_is_not_stale(owner, box):
    update_facility(owner, box.pk, 1, {"capacity_kg": 650})

    again = update_facility(owner, box.pk, 1, {"capacity_kg": 650})

    assert again.version == 2


def test_without_real_changes_the_version_stays_and_no_event_is_left(owner, box):
    same = update_facility(owner, box.pk, 1, {"name": " C-02 "})

    assert same.version == 1
    assert not events(box, "updated").exists()


def test_invalid_values_are_rejected(owner, box):
    with pytest.raises(ValidationError):
        update_facility(owner, box.pk, 1, {"capacity_kg": 0})


def test_a_facility_of_another_producer_does_not_exist(owner):
    with pytest.raises(FacilityNotFound):
        update_facility(owner, PostharvestFacilityFactory().pk, 1, {"name": "C-77"})


def test_an_employee_does_not_reach_a_facility_of_another_farm(box):
    other = FarmFactory(producer=box.farm.producer)
    employee = make_delegate(
        box.farm.producer, ["facilities.change_postharvestfacility"], farm=other
    )

    with pytest.raises(FacilityNotFound):
        update_facility(employee, box.pk, 1, {"name": "C-77"})
