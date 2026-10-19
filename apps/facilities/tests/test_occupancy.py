"""Ocupar y liberar un cajón o una marquesina: lo que fermentación y secado llaman al iniciar y al
finalizar. Aquí se prueban solas, con lotes de prueba."""

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.common.tests.concurrency import run_in_parallel
from apps.facilities.exceptions import (
    FacilityNotFound,
    FacilityNotOccupiedByLot,
    FacilityOtherFarm,
    FacilityUnavailable,
    FacilityWrongType,
    LotAlreadyInFacility,
)
from apps.facilities.models import PostharvestFacility, PostharvestFacilityAuditEvent
from apps.facilities.status import facility_status
from apps.farms.tests.factories import FarmFactory
from apps.lots.tests.factories import LotFactory

from .factories import PostharvestFacilityFactory, lot_in

pytestmark = pytest.mark.django_db

BOX = PostharvestFacility.FacilityType.FERMENTATION_BOX
DRYER = PostharvestFacility.FacilityType.SOLAR_DRYER


@pytest.fixture
def lot():
    return LotFactory()


@pytest.fixture
def box(lot):
    return PostharvestFacilityFactory(farm=lot.harvest.plot.farm, name="C-02")


@pytest.fixture
def owner(lot):
    return make_producer_owner(lot.harvest.plot.farm.producer)


def test_occupying_leaves_the_lot_the_time_a_new_version_and_an_event(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)

    box.refresh_from_db()
    assert (box.current_lot, box.version, facility_status(box)) == (lot, 2, "occupied")
    assert box.occupied_since is not None
    event = PostharvestFacilityAuditEvent.objects.get(facility=box, action="occupied")
    assert event.changes == {"current_lot": {"before": None, "after": str(lot.pk)}}


def test_releasing_leaves_it_available_again(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)
    box.refresh_from_db()

    box.release(lot, actor=owner)

    box.refresh_from_db()
    assert (box.current_lot, box.occupied_since, box.version) == (None, None, 3)
    assert facility_status(box) == "available"
    assert PostharvestFacilityAuditEvent.objects.filter(facility=box, action="released").exists()


def test_an_occupied_facility_is_not_available(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)
    other = lot_in(box.farm)

    with pytest.raises(FacilityUnavailable) as error:
        box.occupy(other, kind=BOX, actor=owner)

    assert error.value.extra["status"] == "occupied"
    assert error.value.extra["lot"]["id"] == str(lot.pk)


def test_an_inactive_facility_is_not_available(owner, lot):
    inactive = PostharvestFacilityFactory(farm=lot.harvest.plot.farm, is_active=False)

    with pytest.raises(FacilityUnavailable) as error:
        inactive.occupy(lot, kind=BOX, actor=owner)

    assert error.value.extra == {"status": "inactive", "lot": None}


def test_a_dryer_is_not_a_box(owner, lot):
    dryer = PostharvestFacilityFactory(farm=lot.harvest.plot.farm, facility_type=DRYER)

    with pytest.raises(FacilityWrongType):
        dryer.occupy(lot, kind=BOX, actor=owner)

    dryer.refresh_from_db()
    assert dryer.current_lot is None


def test_a_facility_of_another_producer_does_not_exist_for_the_lot(owner, lot):
    foreign = PostharvestFacilityFactory()

    with pytest.raises(FacilityNotFound):
        foreign.occupy(lot, kind=BOX, actor=owner)


def test_only_the_lot_inside_releases_the_facility(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)

    with pytest.raises(FacilityNotOccupiedByLot):
        box.release(lot_in(box.farm), actor=owner)

    box.refresh_from_db()
    assert box.current_lot == lot


def test_a_lot_occupies_one_facility_at_a_time(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)
    second = PostharvestFacilityFactory(farm=box.farm, name="C-03")

    with pytest.raises(LotAlreadyInFacility):
        second.occupy(lot, kind=BOX, actor=owner)

    second.refresh_from_db()
    assert second.current_lot_id is None
    assert PostharvestFacilityAuditEvent.objects.filter(facility=second).count() == 0


def test_the_database_keeps_a_lot_in_one_facility(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)
    second = PostharvestFacilityFactory(farm=box.farm, name="C-03")

    with pytest.raises(IntegrityError), transaction.atomic():
        PostharvestFacility.objects.filter(pk=second.pk).update(current_lot=lot)


def test_a_lot_that_left_its_box_enters_the_next_facility(owner, box, lot):
    dryer = PostharvestFacilityFactory(farm=box.farm, name="M-01", facility_type=DRYER)
    box.occupy(lot, kind=BOX, actor=owner)
    box.release(lot, actor=owner)

    dryer.occupy(lot, kind=DRYER, actor=owner)

    dryer.refresh_from_db()
    assert dryer.current_lot_id == lot.pk


def test_the_database_never_keeps_an_inactive_facility_occupied(owner, box, lot):
    box.occupy(lot, kind=BOX, actor=owner)

    with pytest.raises(IntegrityError), transaction.atomic():
        PostharvestFacility.objects.filter(pk=box.pk).update(is_active=False)


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_occupations_of_the_same_box_leave_one():
    first = LotFactory()
    farm = first.harvest.plot.farm
    second = lot_in(farm)
    box = PostharvestFacilityFactory(farm=farm)
    owner = make_producer_owner(farm.producer)

    def attempt(lot):
        try:
            return PostharvestFacility.objects.get(pk=box.pk).occupy(lot, kind=BOX, actor=owner)
        except FacilityUnavailable as error:
            return error

    results = run_in_parallel(attempt, [first, second])

    assert sum(isinstance(result, FacilityUnavailable) for result in results) == 1
    box.refresh_from_db()
    assert box.current_lot_id in {first.pk, second.pk}
    assert PostharvestFacilityAuditEvent.objects.filter(action="occupied").count() == 1


def test_a_lot_only_enters_a_facility_of_its_own_farm(owner, lot):
    other_farm = FarmFactory(producer=lot.harvest.plot.farm.producer)
    elsewhere = PostharvestFacilityFactory(farm=other_farm)

    with pytest.raises(FacilityOtherFarm):
        elsewhere.occupy(lot, kind=BOX, actor=owner)

    elsewhere.refresh_from_db()
    assert elsewhere.current_lot is None
