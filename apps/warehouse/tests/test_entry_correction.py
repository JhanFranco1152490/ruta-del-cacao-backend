"""Corregir el ingreso de un lote mientras las existencias estén intactas."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.models import StockAuditEvent, StockBalance, StockEntry
from apps.warehouse.services.exits import remove_stock

from .factories import WarehouseFactory
from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    estate = WarehouseEstate()
    estate.annex = WarehouseFactory(farm=estate.farm_a, name="Anexo", name_normalized="anexo")
    return estate


def url(lot):
    return f"/api/stock/{lot.pk}/entry"


def correct(client, lot, version=1, **changes):
    return client.patch(url(lot), {"expected_version": version, **changes}, format="json")


def take(estate, grade="g1", quantity="5.0"):
    return remove_stock(
        estate.inspector,
        estate.stored,
        grade,
        Decimal(quantity),
        exit_date=timezone.localdate(),
        reason="sample",
    )


# --- Lo que se corrige ---


def test_correcting_the_location_updates_the_entry_and_the_stock(auth_client, estate):
    response = correct(auth_client(estate.inspector), estate.stored, location="Estante 5")

    assert response.status_code == 200, response.data
    entry = response.data["entry"]
    assert (entry["location"], entry["version"]) == ("Estante 5", 2)
    assert entry["corrected_by"]["id"] == str(estate.inspector.pk)
    assert entry["corrected_at"]
    assert {b.location for b in StockBalance.objects.filter(lot=estate.stored)} == {"Estante 5"}


def test_correcting_the_date(auth_client, estate):
    new_date = timezone.localdate() - timedelta(days=2)

    response = correct(auth_client(estate.inspector), estate.stored, entry_date=str(new_date))

    assert response.status_code == 200, response.data
    assert response.data["entry"]["entry_date"] == str(new_date)


def test_correcting_the_warehouse_moves_the_stock_with_it(auth_client, estate):
    response = correct(
        auth_client(estate.inspector), estate.stored, warehouse_id=str(estate.annex.pk)
    )

    assert response.status_code == 200, response.data
    assert response.data["entry"]["warehouse"]["name"] == "Anexo"
    assert {b.warehouse_id for b in StockBalance.objects.filter(lot=estate.stored)} == {
        estate.annex.pk
    }
    assert StockEntry.objects.get(pk=estate.stored.pk).warehouse_id == estate.annex.pk


def test_the_correction_leaves_the_history_with_the_old_and_new_value(auth_client, estate):
    correct(auth_client(estate.inspector), estate.stored, location="Estante 5")

    event = StockAuditEvent.objects.get(lot=estate.stored, action="entry_corrected")
    assert event.actor == estate.inspector
    assert event.version == 2
    assert event.changes == {"location": {"before": "Estante 3", "after": "Estante 5"}}


def test_correcting_without_changing_anything_writes_nothing(auth_client, estate):
    response = correct(
        auth_client(estate.inspector),
        estate.stored,
        location="  Estante 3 ",
        entry_date=str(estate.entry.entry_date),
    )

    assert response.status_code == 200
    assert response.data["entry"]["version"] == 1
    assert response.data["entry"]["corrected_at"] is None
    assert not StockAuditEvent.objects.filter(lot=estate.stored, action="entry_corrected").exists()


def test_a_deactivated_warehouse_can_stay_where_it_is(auth_client, estate):
    estate.warehouse_a.is_active = False
    estate.warehouse_a.save(update_fields=["is_active"])

    response = correct(
        auth_client(estate.inspector),
        estate.stored,
        warehouse_id=str(estate.warehouse_a.pk),
        location="Estante 6",
    )

    assert response.status_code == 200, response.data


# --- Validaciones ---


def test_the_new_warehouse_must_be_of_the_farm_and_active(auth_client, estate):
    client = auth_client(estate.owner)

    other_farm = correct(client, estate.stored, warehouse_id=str(estate.warehouse_b.pk))
    estate.annex.is_active = False
    estate.annex.save(update_fields=["is_active"])
    inactive = correct(client, estate.stored, warehouse_id=str(estate.annex.pk))

    assert (other_farm.status_code, other_farm.data["code"]) == (400, "warehouse_farm_mismatch")
    assert (inactive.status_code, inactive.data["code"]) == (400, "warehouse_inactive")
    assert StockEntry.objects.get(pk=estate.stored.pk).warehouse_id == estate.warehouse_a.pk


@pytest.mark.parametrize(
    ("days", "message"),
    [
        (1, "La fecha no puede ser futura"),
        (-4, "La fecha no puede ser anterior a la clasificación"),
    ],
)
def test_the_new_date_follows_the_same_rules(auth_client, estate, days, message):
    new_date = timezone.localdate() + timedelta(days=days)

    response = correct(auth_client(estate.inspector), estate.stored, entry_date=str(new_date))

    assert response.status_code == 400
    assert response.data["fields"]["entry_date"] == [message]


def test_a_blank_location_takes_the_location_off(auth_client, estate):
    response = correct(auth_client(estate.inspector), estate.stored, location="  ")

    assert response.status_code == 200, response.data
    assert response.data["entry"]["location"] == ""
    assert not StockBalance.objects.filter(lot=estate.stored).exclude(location="").exists()


def test_the_kilograms_cannot_be_corrected(auth_client, estate):
    response = correct(auth_client(estate.inspector), estate.stored, g1_kg="1.0")

    assert response.status_code == 400
    assert response.data["fields"]["g1_kg"] == ["Campo no permitido."]


def test_the_patch_needs_the_version_and_a_change(auth_client, estate):
    client = auth_client(estate.inspector)

    assert client.patch(url(estate.stored), {"location": "X"}, format="json").status_code == 400
    assert (
        client.patch(url(estate.stored), {"expected_version": 1}, format="json").status_code == 400
    )


# --- Mientras nada haya salido ---


def test_an_exit_in_force_locks_the_entry(auth_client, estate):
    take(estate)

    response = correct(auth_client(estate.inspector), estate.stored, location="Estante 5")

    assert (response.status_code, response.data["code"]) == (409, "entry_has_movements")
    assert StockEntry.objects.get(pk=estate.stored.pk).location == "Estante 3"


def test_the_detail_says_whether_the_entry_can_be_corrected(auth_client, estate):
    client = auth_client(estate.inspector)

    def can_correct():
        return client.get(f"/api/stock/{estate.stored.pk}").data["entry"]["can_correct"]

    assert can_correct() is True
    stock_exit = take(estate)
    assert can_correct() is False
    client.post(
        f"/api/stock/{estate.stored.pk}/exits/{stock_exit.pk}/void",
        {"reason": "Error de digitación"},
        format="json",
    )
    assert can_correct() is True


def test_voiding_the_exit_opens_the_entry_again(auth_client, estate):
    client = auth_client(estate.inspector)
    stock_exit = take(estate)
    client.post(
        f"/api/stock/{estate.stored.pk}/exits/{stock_exit.pk}/void",
        {"reason": "Error de digitación"},
        format="json",
    )

    response = correct(client, estate.stored, location="Estante 5")

    assert response.status_code == 200, response.data


def test_an_exit_of_the_other_grade_also_locks_the_entry(auth_client, estate):
    take(estate, grade="g2", quantity="1.0")

    response = correct(auth_client(estate.inspector), estate.stored, location="Estante 5")

    assert (response.status_code, response.data["code"]) == (409, "entry_has_movements")


# --- Versión, estado, permisos y alcance ---


def test_a_stale_version_returns_the_current_lot(auth_client, estate):
    client = auth_client(estate.inspector)
    correct(client, estate.stored, location="Estante 5")

    response = correct(client, estate.stored, version=1, location="Estante 6")

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["entry"]["location"] == "Estante 5"


def test_a_lot_that_is_not_in_the_warehouse_answers_its_status(auth_client, estate):
    response = correct(auth_client(estate.inspector), estate.classified, location="X")

    assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")
    assert response.data["current_status"] == "classified"


def test_it_needs_a_session_and_the_permission(auth_client, anonymous_client, estate):
    assert anonymous_client.patch(url(estate.stored), {}, format="json").status_code == 401
    viewer = make_delegate(estate.producer, ["warehouse.view_stock"], farm=estate.farm_a)
    assert correct(auth_client(viewer), estate.stored, location="X").status_code == 403


def test_an_employee_of_another_farm_does_not_reach_the_lot(auth_client, estate):
    other = make_delegate(estate.producer, ["warehouse.register_entry"], farm=estate.farm_b)

    assert correct(auth_client(other), estate.stored, location="X").status_code == 404
