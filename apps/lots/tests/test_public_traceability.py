"""La trazabilidad pública de un lote: lo que se arma a partir de su QR, sin cuenta."""

from datetime import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.fermentation.tests.factories import FermentationTurnFactory
from apps.lots.choices import LotStatus
from apps.lots.exceptions import LotNotFound
from apps.lots.public_serializers import PublicLotTraceabilitySerializer
from apps.lots.services.public import public_lot_traceability
from apps.lots.tests.factories import LotQrCodeFactory
from apps.lots.tests.journey import Journey
from apps.quality.models import QualityEvaluation
from apps.quality.tests.factories import LotClassificationFactory

pytestmark = pytest.mark.django_db

TOKEN = "Xq3k9Lm2Pz7tRw1a"


@pytest.fixture
def journey():
    return Journey()


def classified_lot(journey):
    lot = journey.lot(LotStatus.CLASSIFIED)
    journey.fermented(lot)
    journey.dried(lot)
    journey.evaluated(lot)
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal("32.5"),
        g2_kg=Decimal("8.0"),
        discard_kg=Decimal("4.5"),
        discard_reason="mold",
        classified_at=journey.day(17),
    )
    return lot


def published(token=TOKEN):
    return PublicLotTraceabilitySerializer(public_lot_traceability(token)).data


def test_a_stored_lot_shows_its_origin_its_stages_and_its_quality(journey):
    lot = journey.sold_lot()
    LotQrCodeFactory(lot=lot, token=TOKEN)
    local = timezone.localdate

    data = published()

    assert data["origin"] == {
        "farm": "La Esperanza",
        "municipality": "Cúcuta",
        "department": "Norte de Santander",
        "variety": lot.harvest.variety.name,
    }
    assert data["stages"] == [
        {"kind": "harvest", "date": str(lot.harvest.harvest_date)},
        {
            "kind": "fermentation",
            "started_on": str(local(journey.day(1))),
            "ended_on": str(local(journey.day(7))),
            "days": 6,
        },
        {
            "kind": "drying",
            "started_on": str(local(journey.day(7, 1))),
            "ended_on": str(local(journey.day(15))),
            "days": 8,
        },
        {"kind": "evaluation", "date": str(local(journey.day(16)))},
        {"kind": "classification", "date": str(local(journey.day(17)))},
        {"kind": "stock_entry", "date": str(local(journey.day(18)))},
    ]
    assert data["quality"] == {
        "well_fermented_pct": "78.5",
        "g1_pct": "72.2",
        "g2_pct": "17.8",
        "discard_pct": "10.0",
    }


def test_a_classified_lot_has_no_warehouse_stage(journey):
    LotQrCodeFactory(lot=classified_lot(journey), token=TOKEN)

    kinds = [stage["kind"] for stage in published()["stages"]]

    assert kinds == ["harvest", "fermentation", "drying", "evaluation", "classification"]


def test_a_corrected_evaluation_shows_its_current_value(journey):
    lot = classified_lot(journey)
    LotQrCodeFactory(lot=lot, token=TOKEN)
    QualityEvaluation.objects.filter(lot=lot).update(
        well_fermented_pct=Decimal("81.0"),
        corrected_at=journey.day(16, 2),
        corrected_by=journey.owner,
    )

    assert published()["quality"]["well_fermented_pct"] == "81.0"


def test_the_dates_are_local_also_near_midnight(journey):
    lot = classified_lot(journey)
    LotQrCodeFactory(lot=lot, token=TOKEN)
    # Las 9 p. m. en Bogotá ya son el día siguiente en UTC.
    late = timezone.make_aware(datetime(2026, 3, 14, 21, 0))
    lot.fermentation.started_at = late
    lot.fermentation.save(update_fields=["started_at"])

    stages = {stage["kind"]: stage for stage in published()["stages"]}

    assert stages["fermentation"]["started_on"] == "2026-03-14"


def test_an_inactive_producer_keeps_its_page(journey):
    LotQrCodeFactory(lot=journey.sold_lot(), token=TOKEN)
    journey.producer.status = "inactive"
    journey.producer.save(update_fields=["status"])

    assert published()["origin"]["farm"] == "La Esperanza"


@pytest.mark.parametrize(
    "token",
    ["Xq3k9Lm2Pz7tRw1b", "Xq3k9Lm2Pz7tRw1", "Xq3k9Lm2Pz7tRw1aa", "Xq3k9Lm2Pz7tRw1!", "", " " * 16],
)
def test_a_token_that_does_not_exist_or_is_malformed_is_not_found(journey, token):
    LotQrCodeFactory(lot=classified_lot(journey), token=TOKEN)

    with pytest.raises(LotNotFound):
        public_lot_traceability(token)


def test_a_malformed_token_does_not_reach_the_database():
    with CaptureQueriesContext(connection) as queries, pytest.raises(LotNotFound):
        public_lot_traceability("../../etc/passwd")

    assert len(queries) == 0


def test_the_query_count_does_not_grow_with_the_records(journey):
    lot = journey.sold_lot()
    LotQrCodeFactory(lot=lot, token=TOKEN)
    with CaptureQueriesContext(connection) as few:
        published()
    for hours in range(72, 72 + 20 * 6, 6):
        FermentationTurnFactory(process=lot.fermentation, turned_at=journey.day(1, hours))

    with CaptureQueriesContext(connection) as many:
        published()

    assert len(many) == len(few)
