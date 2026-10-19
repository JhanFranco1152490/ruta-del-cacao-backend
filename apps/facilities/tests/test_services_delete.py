import pytest

from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.facilities.exceptions import (
    FacilityHasRecords,
    FacilityNotFound,
    StaleFacilityVersion,
)
from apps.facilities.models import PostharvestFacility, PostharvestFacilityAuditEvent
from apps.facilities.services import delete_facility, update_facility
from apps.farms.tests.factories import FarmFactory

from .factories import PostharvestFacilityFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def box():
    return PostharvestFacilityFactory(name="C-04")


@pytest.fixture
def owner(box):
    return make_producer_owner(box.farm.producer)


def test_a_facility_never_used_is_deleted_and_its_history_survives(owner, box):
    facility_id, farm_id = box.pk, box.farm_id

    delete_facility(owner, facility_id, 1)

    assert not PostharvestFacility.objects.filter(pk=facility_id).exists()
    event = PostharvestFacilityAuditEvent.objects.get(facility_ref=facility_id)
    assert (event.action, event.facility, event.facility_name, event.farm_ref) == (
        "deleted",
        None,
        "C-04",
        farm_id,
    )


def test_a_used_facility_is_not_deleted(used_facility):
    owner = make_producer_owner(used_facility.farm.producer)

    with pytest.raises(FacilityHasRecords):
        delete_facility(owner, used_facility.pk, 1)

    assert PostharvestFacility.objects.filter(pk=used_facility.pk).exists()
    assert not PostharvestFacilityAuditEvent.objects.filter(action="deleted").exists()


def test_a_stale_version_is_not_deleted(owner, box):
    update_facility(owner, box.pk, 1, {"capacity_kg": 650})

    with pytest.raises(StaleFacilityVersion):
        delete_facility(owner, box.pk, 1)

    assert PostharvestFacility.objects.filter(pk=box.pk).exists()


def test_a_facility_of_another_farm_of_the_employee_does_not_exist(box):
    employee = make_delegate(
        box.farm.producer,
        ["facilities.delete_postharvestfacility"],
        farm=FarmFactory(producer=box.farm.producer),
    )

    with pytest.raises(FacilityNotFound):
        delete_facility(employee, box.pk, 1)
