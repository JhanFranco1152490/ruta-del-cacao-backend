"""Lo que el secado agrega a la representación de un lote."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.harvests.tests.factories import HarvestFactory
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.lots.tests.factories import LotFactory
from apps.lots.tests.test_read import Estate

from .factories import DryingProcessFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


def drying_of(lot, **fields):
    return DryingProcessFactory(lot=lot, facility__farm=lot.harvest.plot.farm, **fields)


def test_a_lot_without_drying_shows_none(auth_client, estate):
    detail = auth_client(estate.owner).get(f"/api/lots/{estate.lot_a.pk}").data

    assert detail["drying"] is None


def test_a_lot_in_drying_shows_its_start_and_nothing_of_the_result(auth_client, estate):
    Lot.objects.filter(pk=estate.lot_a.pk).update(status=LotStatus.DRYING)
    process = drying_of(estate.lot_a)

    detail = auth_client(estate.owner).get(f"/api/lots/{estate.lot_a.pk}").data

    assert detail["drying"] == {
        "started_at": timezone.localtime(process.started_at).isoformat(),
        "ended_at": None,
        "final_moisture_pct": None,
        "dry_weight_kg": None,
        "yield_pct": None,
    }


def test_a_dried_lot_shows_its_dry_weight_and_yield(auth_client, estate):
    Lot.objects.filter(pk=estate.lot_a.pk).update(status=LotStatus.DRIED)
    started_at = timezone.now() - timedelta(days=5)
    ended_at = started_at + timedelta(hours=116)
    drying_of(
        estate.lot_a,
        started_at=started_at,
        ended_at=ended_at,
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal("313.2"),
        yield_pct=Decimal("38.2"),
        total_sun_hours=Decimal("31.5"),
    )

    drying = auth_client(estate.owner).get(f"/api/lots/{estate.lot_a.pk}").data["drying"]

    assert drying["ended_at"] == timezone.localtime(ended_at).isoformat()
    assert (drying["final_moisture_pct"], drying["dry_weight_kg"], drying["yield_pct"]) == (
        "7.0",
        "313.2",
        "38.2",
    )


def test_the_lot_list_shows_the_drying_without_more_queries(auth_client, estate):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get("/api/lots")
    for day in range(1, 6):
        harvest = HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 9, day))
        drying_of(LotFactory(harvest=harvest, status=LotStatus.DRYING))

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/lots", {"page_size": 100})

    assert sum(1 for lot in response.data["results"] if lot["drying"]) == 5
    assert len(many) == len(few)
