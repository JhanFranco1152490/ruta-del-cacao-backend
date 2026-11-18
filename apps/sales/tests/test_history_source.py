from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.buyers.tests.factories import BuyerFactory
from apps.common.contracts.lot_history import LotSold, lot_history_source, stage_serializers
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.sales.history import SaleData, SaleLineData
from apps.sales.tests.factories import SaleLineFactory
from apps.sales.tests.helpers import sale_with_lines
from apps.warehouse.tests.factories import StockExitFactory

pytestmark = pytest.mark.django_db

PRICE_KEYS = {"price", "price_per_kg", "subtotal", "total", "total_value", "value"}


def _lot(farm):
    return LotFactory(harvest__plot=characterized_plot(farm=farm), status=LotStatus.IN_WAREHOUSE)


def _history(lot):
    return lot_history_source("sales_history")(lot.pk)


def test_a_lot_without_sales_has_no_sale_stages_and_nothing_sold():
    lot = LotFactory()

    assert _history(lot) == []
    assert lot_history_source("sold_now")(lot.pk) == LotSold(sold_kg=Decimal("0.0"))


def test_a_sale_brings_only_the_lines_of_this_lot():
    farm = FarmFactory()
    lot = _lot(farm)
    buyer = BuyerFactory(producer=farm.producer, name="Chocolates del Oriente S.A.S.")
    sale = sale_with_lines(
        farm, lines=(("g1", "20.0", 18500),), lot=lot, buyer=buyer, sale_date=date(2026, 4, 20)
    )
    # Otra línea de la misma venta, de otro lote.
    other_exit = StockExitFactory(
        lot=_lot(farm), grade="g1", quantity_kg=Decimal("50.0"), reason="sale"
    )
    SaleLineFactory(sale=sale, stock_exit=other_exit)

    [stage] = _history(lot)

    assert (stage.kind, stage.occurred_on, stage.occurred_at, stage.recorded_at) == (
        "sale",
        date(2026, 4, 20),
        None,
        sale.created_at,
    )
    assert stage.data == SaleData(
        sale_id=sale.pk,
        number=sale.code,
        buyer="Chocolates del Oriente S.A.S.",
        lines=(SaleLineData(grade="g1", quantity_kg=Decimal("20.0")),),
        voided_at=None,
        void_reason=None,
    )


def test_a_sale_with_both_grades_of_the_lot_is_one_stage():
    farm = FarmFactory()
    lot = _lot(farm)
    sale_with_lines(farm, lines=(("g2", "8.0", 15000), ("g1", "12.5", 18500)), lot=lot)

    [stage] = _history(lot)

    assert stage.data.lines == (
        SaleLineData(grade="g1", quantity_kg=Decimal("12.5")),
        SaleLineData(grade="g2", quantity_kg=Decimal("8.0")),
    )


def test_a_voided_sale_is_marked_and_does_not_count_as_sold():
    farm = FarmFactory()
    lot = _lot(farm)
    sale_with_lines(farm, lines=(("g1", "20.0", 18500),), lot=lot, sale_date=date(2026, 4, 20))
    voided = sale_with_lines(
        farm, lines=(("g1", "5.0", 18500),), lot=lot, sale_date=date(2026, 4, 22), voided=True
    )

    registered, annulled = _history(lot)

    assert registered.data.voided_at is None
    assert (annulled.data.voided_at, annulled.data.void_reason) == (
        voided.voided_at,
        "Error de digitación",
    )
    assert lot_history_source("sold_now")(lot.pk) == LotSold(sold_kg=Decimal("20.0"))


def test_sales_come_by_date_and_then_by_when_they_were_recorded():
    farm = FarmFactory()
    lot = _lot(farm)
    day = date(2026, 4, 20)
    later = sale_with_lines(farm, lot=lot, sale_date=day + timedelta(days=1))
    second = sale_with_lines(farm, lot=lot, sale_date=day)
    first = sale_with_lines(
        farm, lot=lot, sale_date=day, created_at=second.created_at - timedelta(hours=1)
    )

    assert [stage.data.sale_id for stage in _history(lot)] == [first.pk, second.pk, later.pk]


def test_many_sales_take_the_same_queries(django_assert_num_queries):
    farm = FarmFactory()
    lot = _lot(farm)
    for _ in range(10):
        sale_with_lines(farm, lines=(("g1", "1.0", 18500),), lot=lot)

    with django_assert_num_queries(1):
        stages = _history(lot)
    with django_assert_num_queries(1):
        sold = lot_history_source("sold_now")(lot.pk)

    assert len(stages) == 10
    assert sold == LotSold(sold_kg=Decimal("10.0"))


def test_the_sale_stage_is_serialized_without_any_price():
    farm = FarmFactory()
    lot = _lot(farm)
    sale = sale_with_lines(farm, lines=(("g1", "20", 18500),), lot=lot)
    [stage] = _history(lot)

    data = stage_serializers()["sale"].to_representation(stage.data)

    assert data["number"] == sale.code
    assert data["lines"] == [{"grade": "g1", "quantity_kg": "20.0"}]
    assert not PRICE_KEYS & set(data)
    assert not PRICE_KEYS & set(data["lines"][0])
