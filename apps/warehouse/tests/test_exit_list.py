"""La pestaña Salidas: todas las salidas, filtradas, y lo que sacó cada motivo."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.models import StockExit
from apps.warehouse.services.exits import remove_stock

from .helpers import WarehouseEstate, stored_lot

pytestmark = pytest.mark.django_db

URL = "/api/stock/exits"


@pytest.fixture
def estate():
    """Salidas en A: 5,0 de G1 por muestra hoy, 20,0 de G1 por merma hace 10 días y 3,0 de G2
    por muestra anulada. En B, 7,0 de G1 por reproceso."""
    estate = WarehouseEstate()
    today = timezone.localdate()
    send = lambda lot, grade, kilos, reason, days=0: remove_stock(  # noqa: E731
        estate.inspector,
        lot,
        grade,
        Decimal(kilos),
        exit_date=today - timedelta(days=days),
        reason=reason,
    )
    estate.sample = send(estate.stored, "g1", "5.0", "sample")
    estate.shrinkage = send(estate.stored, "g1", "20.0", "shrinkage")
    # La fecha de la salida no puede ser anterior al ingreso, así que se retrasa después.
    StockExit.objects.filter(pk=estate.shrinkage.pk).update(exit_date=today - timedelta(days=10))
    estate.voided = send(estate.stored, "g2", "3.0", "sample")
    StockExit.objects.filter(pk=estate.voided.pk).update(
        voided_by=estate.inspector, voided_at=timezone.now(), void_reason="Error"
    )
    estate.stored_b, _ = stored_lot(estate.plot_b, estate.warehouse_b, by=estate.inspector)
    estate.reprocessing = send(estate.stored_b, "g1", "7.0", "reprocessing")
    return estate


def ids(response):
    assert response.status_code == 200, response.data
    return [row["id"] for row in response.data["results"]]


def test_the_list_shows_every_exit_from_the_newest(auth_client, estate):
    response = auth_client(estate.owner).get(URL)

    assert set(ids(response)) == {
        str(e.pk) for e in (estate.sample, estate.shrinkage, estate.voided, estate.reprocessing)
    }
    assert ids(response)[-1] == str(estate.shrinkage.pk)


def test_a_row_says_the_lot_the_farm_and_where_the_cacao_is(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"reason": "reprocessing"})

    (row,) = response.data["results"]
    assert row["lot"]["code"] == estate.stored_b.code
    assert row["farm"]["id"] == str(estate.farm_b.pk)
    assert row["warehouse"]["name"] == "Bodega B"
    assert row["quantity_kg"] == "7.0"
    assert row["voided"] is None


def test_the_voided_exits_are_listed_and_marked(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"state": "voided"})

    (row,) = response.data["results"]
    assert row["id"] == str(estate.voided.pk)
    assert row["voided"]["reason"] == "Error"


def test_the_active_state_leaves_the_voided_out(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"state": "active"})

    assert str(estate.voided.pk) not in ids(response)
    assert len(ids(response)) == 3


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"reason": "shrinkage"}, ["shrinkage"]),
        ({"grade": "g2"}, ["voided"]),
        ({"date_from": "recent"}, ["sample", "voided", "reprocessing"]),
        ({"date_to": "old"}, ["shrinkage"]),
    ],
)
def test_the_filters_combine_with_the_listing(auth_client, estate, filters, expected):
    today = timezone.localdate()
    dates = {"recent": today - timedelta(days=3), "old": today - timedelta(days=5)}
    query = {key: str(dates.get(value, value)) for key, value in filters.items()}

    response = auth_client(estate.owner).get(URL, query)

    assert set(ids(response)) == {str(getattr(estate, name).pk) for name in expected}


def test_the_farm_the_warehouse_and_the_code_filters(auth_client, estate):
    client = auth_client(estate.owner)

    by_farm = client.get(URL, {"farm": str(estate.farm_b.pk)})
    by_warehouse = client.get(URL, {"warehouse": str(estate.warehouse_a.pk)})
    by_code = client.get(URL, {"search": estate.stored_b.code.lower()})

    assert ids(by_farm) == [str(estate.reprocessing.pk)]
    assert str(estate.reprocessing.pk) not in ids(by_warehouse)
    assert ids(by_code) == [str(estate.reprocessing.pk)]


def test_a_period_that_ends_before_it_starts_is_refused(auth_client, estate):
    response = auth_client(estate.owner).get(
        URL, {"date_from": "2026-11-05", "date_to": "2026-11-04"}
    )

    assert response.status_code == 400
    assert "date_to" in response.data["fields"]


def test_the_summary_adds_what_left_by_reason_and_skips_the_voided(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/summary")

    assert response.status_code == 200, response.data
    assert response.data["exits"] == 3
    assert response.data["quantity_kg"] == "32.0"
    assert [(r["reason"], r["exits"], r["quantity_kg"]) for r in response.data["by_reason"]] == [
        ("shrinkage", 1, "20.0"),
        ("reprocessing", 1, "7.0"),
        ("sample", 1, "5.0"),
    ]


def test_the_summary_follows_the_filters(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/summary", {"farm": str(estate.farm_b.pk)})

    assert response.data["quantity_kg"] == "7.0"
    assert [r["reason"] for r in response.data["by_reason"]] == ["reprocessing"]


def test_the_summary_without_exits_is_zero(auth_client, estate):
    StockExit.objects.all().delete()

    response = auth_client(estate.owner).get(f"{URL}/summary")

    assert response.data == {"exits": 0, "quantity_kg": "0.0", "by_reason": []}


def test_the_reach_limits_what_is_listed(auth_client, estate):
    other = WarehouseEstate()

    mine = auth_client(estate.owner).get(URL)
    theirs = auth_client(other.owner).get(URL)

    assert len(ids(mine)) == 4
    assert ids(theirs) == []
    assert auth_client(other.owner).get(f"{URL}/summary").data["exits"] == 0


def test_the_quality_manager_sees_only_the_exits_of_its_farms(auth_client, estate):
    response = auth_client(estate.inspector).get(URL)

    assert str(estate.reprocessing.pk) not in ids(response)
    assert len(ids(response)) == 3


def test_without_the_stock_permission_it_is_forbidden(auth_client, estate):
    nobody = make_delegate(estate.producer, ["accounts.users_view"], farm=estate.farm_a)

    assert auth_client(nobody).get(URL).status_code == 403
    assert auth_client(nobody).get(f"{URL}/summary").status_code == 403


def test_the_list_does_not_query_once_per_exit(auth_client, estate):
    client = auth_client(estate.owner)

    def queries():
        with CaptureQueriesContext(connection) as captured:
            assert client.get(URL).status_code == 200
        return len(captured)

    before = queries()
    remove_stock(
        estate.inspector,
        estate.stored,
        "g1",
        Decimal("1.0"),
        exit_date=timezone.localdate(),
        reason="other",
        detail="Prueba",
    )

    assert queries() == before
