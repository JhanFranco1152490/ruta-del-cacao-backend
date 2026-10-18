"""Lo que no se le hace a un elemento mientras un lote lo ocupa, y cómo se muestra."""

from unittest import mock

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.facilities.exceptions import FacilityFieldsLocked, FacilityOccupied
from apps.facilities.models import PostharvestFacility
from apps.facilities.services import delete_facility, update_facility
from apps.lots.tests.factories import LotFactory

from .factories import PostharvestFacilityFactory

pytestmark = pytest.mark.django_db

URL = "/api/postharvest-facilities"


@pytest.fixture
def lot():
    return LotFactory()


@pytest.fixture
def owner(lot):
    return make_producer_owner(lot.harvest.plot.farm.producer)


@pytest.fixture
def occupied(owner, lot):
    box = PostharvestFacilityFactory(farm=lot.harvest.plot.farm, name="C-02")
    box.occupy(lot, kind=PostharvestFacility.FacilityType.FERMENTATION_BOX, actor=owner)
    box.refresh_from_db()
    return box


def test_an_occupied_facility_is_not_deactivated_and_the_lot_is_named(owner, occupied, lot):
    with pytest.raises(FacilityOccupied) as error:
        update_facility(owner, occupied.pk, occupied.version, {"is_active": False})

    assert error.value.extra["lot"] == {"id": str(lot.pk), "code": lot.code, "status": lot.status}
    occupied.refresh_from_db()
    assert (occupied.is_active, occupied.current_lot) == (True, lot)


def test_an_occupied_facility_keeps_its_type(owner, occupied):
    with pytest.raises(FacilityFieldsLocked):
        update_facility(owner, occupied.pk, occupied.version, {"facility_type": "solar_dryer"})


def test_an_occupied_facility_still_changes_its_name_and_capacity(owner, occupied):
    updated = update_facility(
        owner, occupied.pk, occupied.version, {"name": "C-20", "capacity_kg": 700}
    )

    assert (updated.name, updated.capacity_kg, updated.current_lot_id) == (
        "C-20",
        700,
        occupied.current_lot_id,
    )


def test_an_occupied_facility_is_not_deleted(owner, occupied):
    with pytest.raises(FacilityOccupied):
        delete_facility(owner, occupied.pk, occupied.version)

    assert PostharvestFacility.objects.filter(pk=occupied.pk).exists()


def test_the_api_shows_the_lot_inside_and_the_farm_code(auth_client, owner, occupied, lot):
    response = auth_client(owner).get(f"{URL}/{occupied.pk}")

    assert response.data["status"] == "occupied"
    assert response.data["occupied_by"] == {
        "lot": {"id": str(lot.pk), "code": lot.code, "status": "generated"},
        "since": response.data["occupied_by"]["since"],
    }
    assert response.data["farm"]["code"] == occupied.farm.code


def test_a_free_facility_has_no_lot(auth_client, owner, lot):
    free = PostharvestFacilityFactory(farm=lot.harvest.plot.farm)

    assert auth_client(owner).get(f"{URL}/{free.pk}").data["occupied_by"] is None


def test_deactivating_an_occupied_facility_in_the_api_names_the_lot(
    auth_client, owner, occupied, lot
):
    response = auth_client(owner).patch(
        f"{URL}/{occupied.pk}",
        {"expected_version": occupied.version, "is_active": False},
        format="json",
    )

    assert (response.status_code, response.data["code"]) == (409, "facility_occupied")
    assert response.data["lot"]["code"] == lot.code


def test_deleting_an_occupied_facility_in_the_api_is_refused(auth_client, owner, occupied):
    response = auth_client(owner).delete(
        f"{URL}/{occupied.pk}?expected_version={occupied.version}"
    )

    assert (response.status_code, response.data["code"]) == (409, "facility_occupied")


def occupy_in_the_middle(facility, lot):
    """Ocupa el elemento en la base mientras el servicio ya lo leyó libre: lo que pasaría si quien
    llama a `occupy` no tomara el bloqueo de la finca."""

    def is_used(_):
        PostharvestFacility.objects.filter(pk=facility.pk).update(
            current_lot=lot, occupied_since=timezone.now()
        )
        return False

    return is_used


def test_deactivating_while_it_gets_occupied_answers_occupied(owner, lot):
    free = PostharvestFacilityFactory(farm=lot.harvest.plot.farm, name="C-05")

    with mock.patch(
        "apps.facilities.services.update.is_used", side_effect=occupy_in_the_middle(free, lot)
    ):
        with pytest.raises(FacilityOccupied) as error:
            update_facility(owner, free.pk, 1, {"is_active": False})

    assert error.value.extra["lot"]["id"] == str(lot.pk)


def test_deleting_while_it_gets_occupied_answers_occupied(owner, lot):
    free = PostharvestFacilityFactory(farm=lot.harvest.plot.farm, name="C-06")

    with mock.patch(
        "apps.facilities.services.delete.is_used", side_effect=occupy_in_the_middle(free, lot)
    ):
        with pytest.raises(FacilityOccupied):
            delete_facility(owner, free.pk, 1)

    assert PostharvestFacility.objects.filter(pk=free.pk).exists()
