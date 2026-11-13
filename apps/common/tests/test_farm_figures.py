import uuid
from decimal import Decimal

from apps.common.contracts.indicators import (
    FarmMonthSales,
    FarmQuality,
    PlotMonthDried,
    PlotMonthKg,
)
from apps.common.farm_figures import FarmFigures, figures_by_farm

FARM_A = uuid.uuid4()
FARM_B = uuid.uuid4()
PLOT_A1 = uuid.uuid4()
PLOT_A2 = uuid.uuid4()


def _harvested(farm, plot, kg, month="2026-03"):
    return PlotMonthKg(plot_id=plot, farm_id=farm, month=month, kg=Decimal(kg))


def test_adds_each_source_by_farm_across_plots_and_months():
    figures = figures_by_farm(
        harvested=[
            _harvested(FARM_A, PLOT_A1, "100.0"),
            _harvested(FARM_A, PLOT_A2, "50.0", month="2026-04"),
        ],
        dried=[
            PlotMonthDried(
                plot_id=PLOT_A1,
                farm_id=FARM_A,
                month="2026-03",
                dry_kg=Decimal("33.0"),
                green_kg=Decimal("100.0"),
            )
        ],
        quality=[
            FarmQuality(
                farm_id=FARM_A,
                g1_kg=Decimal("20.0"),
                g2_kg=Decimal("8.0"),
                discard_kg=Decimal("5.0"),
                lots_classified=1,
                lots_discarded=0,
            )
        ],
        sales=[
            FarmMonthSales(
                farm_id=FARM_A, month="2026-05", g1_kg=Decimal("10.0"), g2_kg=Decimal("0"), sales=1
            ),
            FarmMonthSales(
                farm_id=FARM_A,
                month="2026-06",
                g1_kg=Decimal("5.0"),
                g2_kg=Decimal("3.0"),
                sales=2,
            ),
        ],
    )

    assert set(figures) == {FARM_A}
    farm = figures[FARM_A]
    assert farm.green_kg == Decimal("150.0")
    assert farm.dry_kg == Decimal("33.0")
    assert farm.green_kg_not_dried == Decimal("50.0")
    assert (farm.g1_kg, farm.g2_kg, farm.discard_kg) == (
        Decimal("20.0"),
        Decimal("8.0"),
        Decimal("5.0"),
    )
    assert (farm.lots_classified, farm.lots_discarded) == (1, 0)
    assert (farm.sold_g1_kg, farm.sold_g2_kg, farm.sold_kg) == (
        Decimal("15.0"),
        Decimal("3.0"),
        Decimal("18.0"),
    )
    assert farm.sales == 3


def test_a_farm_with_only_one_source_gets_zeros_in_the_rest():
    figures = figures_by_farm(
        harvested=[],
        dried=[],
        quality=[],
        sales=[
            FarmMonthSales(
                farm_id=FARM_B, month="2026-05", g1_kg=Decimal("0"), g2_kg=Decimal("4.0"), sales=1
            )
        ],
    )

    assert figures == {
        FARM_B: FarmFigures(sold_g2_kg=Decimal("4.0"), sales=1),
    }
    assert figures[FARM_B].green_kg == Decimal("0")


def test_without_rows_there_are_no_farms():
    assert figures_by_farm(harvested=[], dried=[], quality=[], sales=[]) == {}
