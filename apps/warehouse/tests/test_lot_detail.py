"""Lo que bodega agrega a la representación del lote."""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.warehouse.models import StockBalance

from .helpers import WarehouseEstate, stored_lot

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return WarehouseEstate()


def test_a_lot_that_has_not_entered_has_no_warehouse(auth_client, estate):
    response = auth_client(estate.owner).get(f"/api/lots/{estate.classified.pk}")

    assert response.status_code == 200
    assert response.data["warehouse"] is None


def test_a_stored_lot_says_where_it_is_and_how_much_there_is(auth_client, estate):
    response = auth_client(estate.owner).get(f"/api/lots/{estate.stored.pk}")

    warehouse = response.data["warehouse"]
    assert warehouse["warehouse_name"] == "Bodega A"
    assert warehouse["location"] == "Estante 3"
    assert warehouse["entry_date"] == str(estate.entry.entry_date)
    assert (warehouse["g1_entered_kg"], warehouse["g2_entered_kg"]) == ("250.0", "55.2")
    assert (warehouse["g1_available_kg"], warehouse["g2_available_kg"]) == ("250.0", "55.2")


def test_the_available_kilograms_follow_the_exits_and_a_grade_in_zero_reads_zero(
    auth_client, estate
):
    only_g1, _ = stored_lot(estate.plot_a, estate.warehouse_a, g1="100.0", g2="0.0")
    StockBalance.objects.filter(lot=estate.stored, grade="g1").update(quantity_kg=Decimal("40.0"))
    client = auth_client(estate.owner)

    taken = client.get(f"/api/lots/{estate.stored.pk}").data["warehouse"]
    zero = client.get(f"/api/lots/{only_g1.pk}").data["warehouse"]

    assert (taken["g1_available_kg"], taken["g1_entered_kg"]) == ("40.0", "250.0")
    assert (zero["g2_entered_kg"], zero["g2_available_kg"]) == ("0.0", "0.0")


def test_the_list_carries_the_field_and_filters_by_the_new_status(auth_client, estate):
    client = auth_client(estate.owner)

    listed = client.get("/api/lots", {"status": "in_warehouse"})

    assert listed.status_code == 200, listed.data
    assert [row["id"] for row in listed.data["results"]] == [str(estate.stored.pk)]
    assert listed.data["results"][0]["warehouse"]["location"] == "Estante 3"


def test_the_summary_counts_the_lots_in_the_warehouse(auth_client, estate):
    response = auth_client(estate.owner).get("/api/lots/summary")

    counts = {row["status"]: row["count"] for row in response.data["results"]}
    assert counts["in_warehouse"] == 1
    assert counts["classified"] == 4


def test_the_list_does_not_make_queries_for_each_lot(auth_client, estate):
    for _ in range(3):
        stored_lot(estate.plot_a, estate.warehouse_a)
    client = auth_client(estate.owner)
    client.get("/api/lots")  # abre la sesión y calienta lo que el primer pedido carga

    def queries(page_size):
        with CaptureQueriesContext(connection) as captured:
            response = client.get("/api/lots", {"status": "in_warehouse", "page_size": page_size})
        assert response.status_code == 200
        return len(captured)

    assert queries(1) == queries(100)
