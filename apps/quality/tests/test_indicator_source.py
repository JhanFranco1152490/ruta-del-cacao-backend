from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.common.contracts.indicators import FarmQuality, IndicatorPeriod, indicator_source
from apps.drying.tests.factories import DryingProcessFactory
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.quality.tests.factories import LotClassificationFactory, LotDiscardFactory

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))
BOGOTA = ZoneInfo("America/Bogota")


def farm_ids(*farms):
    return Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")


def at(*moment):
    return datetime(*moment, tzinfo=BOGOTA)


def lot_of(farm, status, dry_kg=Decimal("100.0")):
    lot = LotFactory(harvest__plot=characterized_plot(farm=farm), status=status)
    DryingProcessFactory(
        lot=lot,
        ended_at=timezone.now(),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=dry_kg,
        yield_pct=Decimal("35.0"),
        total_sun_hours=Decimal("40.0"),
    )
    return lot


def classified(farm, g1, g2, discard, when, status=LotStatus.CLASSIFIED):
    lot = lot_of(farm, status, dry_kg=g1 + g2 + discard)
    LotClassificationFactory(
        lot=lot,
        g1_kg=g1,
        g2_kg=g2,
        discard_kg=discard,
        discard_reason="mold" if discard else "",
        classified_at=when,
    )
    return lot


def test_the_classifications_and_whole_discards_add_up_by_farm(django_assert_num_queries):
    farm = FarmFactory()
    classified(farm, Decimal("80.0"), Decimal("15.0"), Decimal("5.0"), at(2026, 1, 10, 9))
    # Ya en bodega sigue siendo un lote clasificado.
    classified(
        farm,
        Decimal("40.0"),
        Decimal("10.0"),
        Decimal("0.0"),
        at(2026, 2, 3, 9),
        status=LotStatus.IN_WAREHOUSE,
    )
    LotDiscardFactory(
        lot=lot_of(farm, LotStatus.DISCARDED, Decimal("30.0")), discarded_at=at(2026, 3, 1, 9)
    )

    with django_assert_num_queries(1):
        rows = indicator_source("quality")(farm_ids(farm), PERIOD)

    assert rows == [
        FarmQuality(
            farm_id=farm.pk,
            g1_kg=Decimal("120.0"),
            g2_kg=Decimal("25.0"),
            discard_kg=Decimal("35.0"),
            lots_classified=2,
            lots_discarded=1,
        )
    ]


def test_the_closing_day_is_the_local_one_at_both_ends():
    farm = FarmFactory()
    classified(farm, Decimal("10.0"), Decimal("0.0"), Decimal("0.0"), at(2026, 1, 1, 0, 5))
    classified(farm, Decimal("20.0"), Decimal("0.0"), Decimal("0.0"), at(2026, 3, 31, 23, 50))
    classified(farm, Decimal("40.0"), Decimal("0.0"), Decimal("0.0"), at(2025, 12, 31, 23, 50))
    classified(farm, Decimal("80.0"), Decimal("0.0"), Decimal("0.0"), at(2026, 4, 1, 0, 5))

    [row] = indicator_source("quality")(farm_ids(farm), PERIOD)

    assert row.g1_kg == Decimal("30.0")
    assert row.lots_classified == 2


def test_lots_of_other_farms_or_still_open_do_not_count():
    farm = FarmFactory()
    classified(FarmFactory(), Decimal("10.0"), Decimal("0.0"), Decimal("0.0"), at(2026, 2, 1, 9))
    lot_of(farm, LotStatus.EVALUATED)

    assert indicator_source("quality")(farm_ids(farm), PERIOD) == []
