"""Ingresar a bodega un lote Clasificado (HU-38)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.models import StockAuditEvent, StockBalance, StockEntry

from .factories import WarehouseFactory
from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return WarehouseEstate()


def url(lot):
    return f"/api/stock/{lot.pk}/entry"


def body(lot, warehouse, **overrides):
    return {
        "expected_lot_version": lot.version,
        "entry_date": str(timezone.localdate()),
        "warehouse_id": str(warehouse.pk),
        "location": "Estante 3",
        **overrides,
    }


def enter(client, lot, warehouse, **overrides):
    return client.post(url(lot), body(lot, warehouse, **overrides), format="json")


# --- Caso feliz ---


def test_entering_a_classified_lot_leaves_it_in_the_warehouse(auth_client, estate):
    lot = estate.classified

    response = enter(auth_client(estate.inspector), lot, estate.warehouse_a)

    assert response.status_code == 201, response.data
    assert response.data["lot"]["status"] == "in_warehouse"
    entry = response.data["entry"]
    assert (entry["g1_kg"], entry["g2_kg"]) == ("250.0", "55.2")
    assert (entry["location"], entry["warehouse"]["name"]) == ("Estante 3", "Bodega A")
    assert entry["entered_by"]["id"] == str(estate.inspector.pk)
    assert [(b["grade"], b["quantity_kg"]) for b in response.data["balances"]] == [
        ("g1", "250.0"),
        ("g2", "55.2"),
    ]
    assert response.data["exits"] == []
    lot.refresh_from_db()
    assert lot.status == "in_warehouse"


def test_the_stock_of_each_grade_starts_at_what_was_classified(auth_client, estate):
    enter(auth_client(estate.inspector), estate.classified, estate.warehouse_a)

    balances = StockBalance.objects.filter(lot=estate.classified).order_by("grade")
    assert [(b.grade, str(b.quantity_kg), b.location) for b in balances] == [
        ("g1", "250.0", "Estante 3"),
        ("g2", "55.2", "Estante 3"),
    ]
    assert {b.warehouse_id for b in balances} == {estate.warehouse_a.pk}


def test_a_grade_in_zero_gets_no_stock_row(auth_client, estate):
    response = enter(auth_client(estate.inspector), estate.classified_g1_only, estate.warehouse_a)

    assert response.status_code == 201, response.data
    assert [(b["grade"], b["quantity_kg"]) for b in response.data["balances"]] == [("g1", "300.0")]
    assert StockBalance.objects.filter(lot=estate.classified_g1_only).count() == 1


def test_entering_leaves_the_history(auth_client, estate):
    lot = estate.classified

    enter(auth_client(estate.inspector), lot, estate.warehouse_a)

    event = StockAuditEvent.objects.get(lot=lot, action="entered")
    assert event.actor == estate.inspector
    assert event.changes["location"] == {"before": None, "after": "Estante 3"}
    assert event.changes["g1_kg"] == {"before": None, "after": "250.0"}
    status = lot.audit_events.get(action="status_changed")
    assert status.changes == {"status": {"before": "classified", "after": "in_warehouse"}}


def test_the_owner_and_the_technical_account_can_enter_too(auth_client, estate):
    from apps.accounts.tests.factories import UserFactory

    owner_response = enter(auth_client(estate.owner), estate.classified_b, estate.warehouse_b)
    technical = UserFactory(is_superuser=True, producer=None)
    lot = estate.classified
    technical_response = enter(auth_client(technical), lot, estate.warehouse_a)

    assert owner_response.status_code == 201
    assert technical_response.status_code == 201


# --- Fecha ---


def test_the_entry_may_be_on_the_day_of_the_classification(auth_client, estate):
    day = timezone.localdate() - timedelta(days=3)

    response = enter(
        auth_client(estate.inspector), estate.classified, estate.warehouse_a, entry_date=str(day)
    )

    assert response.status_code == 201, response.data


def test_a_future_date_is_refused(auth_client, estate):
    tomorrow = timezone.localdate() + timedelta(days=1)

    response = enter(
        auth_client(estate.inspector),
        estate.classified,
        estate.warehouse_a,
        entry_date=str(tomorrow),
    )

    assert response.status_code == 400
    assert response.data["fields"]["entry_date"] == ["La fecha no puede ser futura"]
    assert not StockEntry.objects.filter(lot=estate.classified).exists()


def test_a_date_before_the_classification_is_refused(auth_client, estate):
    before = timezone.localdate() - timedelta(days=4)

    response = enter(
        auth_client(estate.inspector),
        estate.classified,
        estate.warehouse_a,
        entry_date=str(before),
    )

    assert response.status_code == 400
    assert response.data["fields"]["entry_date"] == [
        "La fecha no puede ser anterior a la clasificación"
    ]
    estate.classified.refresh_from_db()
    assert estate.classified.status == "classified"


# --- Campos obligatorios (CA-03) ---


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("entry_date", "Este campo es requerido."),
        ("warehouse_id", "Elija la bodega"),
        ("expected_lot_version", "Este campo es requerido."),
    ],
)
def test_a_missing_field_is_named_and_nothing_is_saved(auth_client, estate, missing, message):
    payload = body(estate.classified, estate.warehouse_a)
    del payload[missing]

    response = auth_client(estate.inspector).post(url(estate.classified), payload, format="json")

    assert response.status_code == 400
    assert response.data["fields"][missing] == [message]
    assert not StockEntry.objects.filter(lot=estate.classified).exists()


@pytest.mark.parametrize("location", ["   ", None])
def test_the_location_is_optional(auth_client, estate, location):
    payload = body(estate.classified, estate.warehouse_a)
    if location is None:
        del payload["location"]
    else:
        payload["location"] = location

    response = auth_client(estate.inspector).post(url(estate.classified), payload, format="json")

    assert response.status_code == 201, response.data
    assert StockEntry.objects.get(lot=estate.classified).location == ""
    assert response.data["entry"]["location"] == ""
    assert StockBalance.objects.filter(lot=estate.classified, location="").count() == 2


def test_a_location_longer_than_sixty_is_refused(auth_client, estate):
    response = enter(
        auth_client(estate.inspector), estate.classified, estate.warehouse_a, location="x" * 61
    )

    assert response.status_code == 400
    assert "location" in response.data["fields"]


def test_a_field_that_cannot_be_written_is_refused(auth_client, estate):
    response = enter(
        auth_client(estate.inspector), estate.classified, estate.warehouse_a, g1_kg="1.0"
    )

    assert response.status_code == 400
    assert response.data["fields"]["g1_kg"] == ["Campo no permitido."]


# --- La bodega ---


def test_a_warehouse_of_another_farm_is_refused(auth_client, estate):
    response = enter(auth_client(estate.owner), estate.classified, estate.warehouse_b)

    assert (response.status_code, response.data["code"]) == (400, "warehouse_farm_mismatch")
    assert response.data["fields"]["warehouse_id"]


def test_a_deactivated_warehouse_does_not_receive_lots(auth_client, estate):
    estate.warehouse_a.is_active = False
    estate.warehouse_a.save(update_fields=["is_active"])

    response = enter(auth_client(estate.inspector), estate.classified, estate.warehouse_a)

    assert (response.status_code, response.data["code"]) == (400, "warehouse_inactive")


def test_a_warehouse_of_another_producer_does_not_exist(auth_client, estate):
    foreign = WarehouseFactory()

    response = enter(auth_client(estate.owner), estate.classified, foreign)

    assert response.status_code == 404


def test_a_warehouse_that_does_not_exist_is_not_found(auth_client, estate):
    payload = body(
        estate.classified, estate.warehouse_a, warehouse_id="3f8a1b2c-0000-4000-8000-000000000000"
    )

    response = auth_client(estate.owner).post(url(estate.classified), payload, format="json")

    assert response.status_code == 404


# --- El lote ---


@pytest.mark.parametrize("attribute", ["stored", "classified_b"])
def test_a_lot_that_is_not_classified_or_not_reachable(auth_client, estate, attribute):
    lot = getattr(estate, attribute)

    response = enter(auth_client(estate.inspector), lot, estate.warehouse_a)

    if attribute == "stored":
        assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")
        assert response.data["current_status"] == "in_warehouse"
    else:
        assert response.status_code == 404


def test_a_lot_that_is_still_being_worked_answers_its_status(auth_client, estate):
    from apps.lots.choices import LotStatus
    from apps.quality.tests.helpers import dried_lot

    lot = dried_lot(estate.plot_a, status=LotStatus.EVALUATED)

    response = enter(auth_client(estate.inspector), lot, estate.warehouse_a)

    assert (response.status_code, response.data["current_status"]) == (409, "evaluated")


def test_entering_twice_is_refused_and_the_stock_does_not_double(auth_client, estate):
    client = auth_client(estate.inspector)
    lot = estate.classified
    first = enter(client, lot, estate.warehouse_a)

    second = client.post(
        url(lot),
        body(lot, estate.warehouse_a, expected_lot_version=first.data["lot"]["version"]),
        format="json",
    )

    assert (second.status_code, second.data["code"]) == (409, "lot_invalid_status")
    assert StockBalance.objects.filter(lot=lot, grade="g1").get().quantity_kg == 250


def test_a_lot_without_kilograms_has_nothing_to_store(auth_client, estate):
    response = enter(auth_client(estate.inspector), estate.classified_empty, estate.warehouse_a)

    assert (response.status_code, response.data["code"]) == (409, "lot_nothing_to_store")
    estate.classified_empty.refresh_from_db()
    assert estate.classified_empty.status == "classified"


def test_an_old_lot_version_is_refused(auth_client, estate):
    lot = estate.classified

    response = auth_client(estate.inspector).post(
        url(lot),
        body(lot, estate.warehouse_a, expected_lot_version=lot.version + 5),
        format="json",
    )

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert not StockEntry.objects.filter(lot=lot).exists()


# --- Permisos y alcance ---


def test_it_needs_a_session(anonymous_client, estate):
    assert anonymous_client.post(url(estate.classified), {}, format="json").status_code == 401


def test_without_the_permission_it_is_forbidden(auth_client, estate):
    viewer = make_delegate(estate.producer, ["warehouse.view_stock"], farm=estate.farm_a)

    response = enter(auth_client(viewer), estate.classified, estate.warehouse_a)

    assert response.status_code == 403
    assert not StockEntry.objects.filter(lot=estate.classified).exists()


def test_an_employee_of_another_farm_does_not_reach_the_lot(auth_client, estate):
    other = make_delegate(estate.producer, ["warehouse.register_entry"], farm=estate.farm_b)

    response = enter(auth_client(other), estate.classified, estate.warehouse_a)

    assert response.status_code == 404


def test_a_failure_leaves_nothing_behind(auth_client, estate):
    lot = estate.classified

    enter(auth_client(estate.inspector), lot, estate.warehouse_a, entry_date="2099-01-01")

    assert not StockEntry.objects.filter(lot=lot).exists()
    assert not StockBalance.objects.filter(lot=lot).exists()
    assert not StockAuditEvent.objects.filter(lot=lot).exists()
    assert not lot.audit_events.filter(action="status_changed").exists()


# --- Por ingresar ---


def test_the_pending_list_has_the_classified_lots_with_kilograms(auth_client, estate):
    response = auth_client(estate.inspector).get("/api/stock/pending-entry")

    assert response.status_code == 200, response.data
    ids = [row["lot"]["id"] for row in response.data["results"]]
    assert set(ids) == {str(estate.classified.pk), str(estate.classified_g1_only.pk)}
    row = next(r for r in response.data["results"] if r["lot"]["id"] == str(estate.classified.pk))
    assert (row["g1_kg"], row["g2_kg"]) == ("250.0", "55.2")
    assert row["farm"]["id"] == str(estate.farm_a.pk)
    assert row["classified_at"]


def test_the_pending_list_leaves_out_the_lot_without_kilograms_and_the_ones_stored(
    auth_client, estate
):
    response = auth_client(estate.owner).get("/api/stock/pending-entry")

    ids = {row["lot"]["id"] for row in response.data["results"]}
    assert str(estate.classified_empty.pk) not in ids
    assert str(estate.stored.pk) not in ids
    assert str(estate.classified_b.pk) in ids


def test_the_pending_list_filters_and_follows_the_scope(auth_client, estate):
    client = auth_client(estate.owner)

    by_farm = client.get("/api/stock/pending-entry", {"farm": str(estate.farm_b.pk)})
    by_code = client.get(
        "/api/stock/pending-entry", {"search": estate.classified_b.code[-5:].lower()}
    )

    assert [r["lot"]["id"] for r in by_farm.data["results"]] == [str(estate.classified_b.pk)]
    assert [r["lot"]["id"] for r in by_code.data["results"]] == [str(estate.classified_b.pk)]


def test_the_pending_list_needs_the_entry_permission(auth_client, estate):
    viewer = make_delegate(estate.producer, ["warehouse.view_stock"], farm=estate.farm_a)

    assert auth_client(viewer).get("/api/stock/pending-entry").status_code == 403


def test_the_pending_list_goes_from_the_oldest_classification(auth_client, estate):
    from apps.quality.models import LotClassification

    LotClassification.objects.filter(lot=estate.classified_g1_only).update(
        classified_at=timezone.now() - timedelta(days=9)
    )

    response = auth_client(estate.inspector).get("/api/stock/pending-entry")

    assert [r["lot"]["id"] for r in response.data["results"]][0] == str(
        estate.classified_g1_only.pk
    )


# --- Detalle ---


def test_the_detail_of_a_classified_lot_has_no_entry_yet(auth_client, estate):
    response = auth_client(estate.inspector).get(f"/api/stock/{estate.classified.pk}")

    assert response.status_code == 200, response.data
    assert response.data["entry"] is None
    assert (response.data["balances"], response.data["exits"]) == ([], [])
    assert response.data["classified"]["g1_kg"] == "250.0"


def test_the_detail_of_a_stored_lot_shows_entry_and_stock(auth_client, estate):
    response = auth_client(estate.inspector).get(f"/api/stock/{estate.stored.pk}")

    assert response.status_code == 200, response.data
    assert response.data["entry"]["warehouse"]["name"] == "Bodega A"
    assert response.data["entry"]["can_correct"] is True
    assert {b["grade"] for b in response.data["balances"]} == {"g1", "g2"}


def test_the_detail_of_a_lot_before_classification_does_not_exist(auth_client, estate):
    from apps.lots.choices import LotStatus
    from apps.quality.tests.helpers import dried_lot

    lot = dried_lot(estate.plot_a, status=LotStatus.EVALUATED)

    assert auth_client(estate.inspector).get(f"/api/stock/{lot.pk}").status_code == 404
