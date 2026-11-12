import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.role_helpers import make_administrator
from apps.common.contracts.indicators import IndicatorPeriod
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.indicators.services import association_indicators
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory
from apps.quality.tests.factories import LotClassificationFactory, LotDiscardFactory
from apps.reports.exceptions import ReportFilterNotFound
from apps.reports.report import ReportFilter
from apps.reports.request_serializers import AssociationReportQuerySerializer
from apps.reports.services import association_report
from apps.sales.tests.helpers import sale_with_lines

from .helpers import PERIOD, at, dry, harvest

pytestmark = pytest.mark.django_db

FORBIDDEN_KEYS = ("plot", "lot", "stock", "warehouse", "price", "subtotal", "value")


def generate(actor, **query):
    serializer = AssociationReportQuerySerializer(data=query)
    serializer.is_valid(raise_exception=True)
    return association_report(actor, serializer.validated_data)


def totals(report):
    return {total.key: total.value for total in report.totals}


class Association:
    """Dos productores: Rosa con La Esperanza (Cúcuta) y El Mirador (Ocaña), y Luis con Villa Luz
    (Cúcuta), que no produjo nada en el periodo."""

    def __init__(self):
        self.admin = make_administrator()
        self.rosa = ProducerFactory(first_name="Rosa", last_name="Quintero")
        self.luis = ProducerFactory(first_name="Luis", last_name="Gómez")
        self.esperanza = FarmFactory(
            producer=self.rosa, number=1, name="La Esperanza", municipality_code="54001"
        )
        self.mirador = FarmFactory(
            producer=self.rosa, number=2, name="El Mirador", municipality_code="54498"
        )
        self.villa_luz = FarmFactory(
            producer=self.luis, number=1, name="Villa Luz", municipality_code="54001"
        )
        self.rio = characterized_plot(farm=self.esperanza)
        self.alto = characterized_plot(farm=self.mirador)


@pytest.fixture
def association():
    return Association()


def classify(plot, g1, g2, discard, when):
    lot = LotFactory(harvest__plot=plot, status=LotStatus.CLASSIFIED)
    dry(lot, Decimal(g1) + Decimal(g2) + Decimal(discard))
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal(g1),
        g2_kg=Decimal(g2),
        discard_kg=Decimal(discard),
        discard_reason="mold" if Decimal(discard) else "",
        classified_at=when,
    )


def test_the_production_report_has_a_row_per_farm_also_in_zero(association):
    dry(LotFactory(harvest=harvest(association.rio, date(2026, 2, 1), "100.0")), "35.0")
    harvest(association.rio, date(2026, 2, 2), "20.0")
    harvest(association.alto, date(2026, 3, 1), "300.0")

    report = generate(association.admin, type="production", **PERIOD)

    assert [(column.key, column.kind) for column in report.columns] == [
        ("farm", "text"),
        ("municipality", "text"),
        ("producer", "text"),
        ("green_kg", "kg"),
        ("dry_kg", "kg"),
        ("green_kg_not_dried", "kg"),
    ]
    assert report.rows == [
        {
            "farm": "F02 · El Mirador",
            "municipality": "Ocaña",
            "producer": f"{association.rosa.member_code} · Rosa Quintero",
            "green_kg": Decimal("300.0"),
            "dry_kg": Decimal("0.0"),
            "green_kg_not_dried": Decimal("300.0"),
        },
        {
            "farm": "F01 · La Esperanza",
            "municipality": "Cúcuta",
            "producer": f"{association.rosa.member_code} · Rosa Quintero",
            "green_kg": Decimal("120.0"),
            "dry_kg": Decimal("35.0"),
            "green_kg_not_dried": Decimal("20.0"),
        },
        {
            "farm": "F01 · Villa Luz",
            "municipality": "Cúcuta",
            "producer": f"{association.luis.member_code} · Luis Gómez",
            "green_kg": Decimal("0.0"),
            "dry_kg": Decimal("0.0"),
            "green_kg_not_dried": Decimal("0.0"),
        },
    ]
    assert totals(report) == {
        "producers": 2,
        "farms": 3,
        "green_kg": Decimal("420.0"),
        "dry_kg": Decimal("35.0"),
        "green_kg_not_dried": Decimal("320.0"),
    }


def test_without_any_figure_there_is_no_report(association):
    harvest(association.rio, date(2025, 12, 31), "100.0")

    report = generate(association.admin, type="production", **PERIOD)

    assert report.is_empty
    assert totals(report)["green_kg"] == Decimal("0.0")


def test_an_inactive_farm_shows_only_with_figures(association):
    association.villa_luz.is_active = False
    association.villa_luz.save()
    gone = FarmFactory(producer=association.luis, number=2, is_active=False)
    harvest(characterized_plot(farm=gone), date(2026, 2, 1), "5.0")
    harvest(association.rio, date(2026, 2, 1), "1.0")

    farms = [row["farm"] for row in generate(association.admin, type="production", **PERIOD).rows]

    assert farms == [f"F02 · {gone.name}", "F01 · La Esperanza", "F02 · El Mirador"]


def test_the_farms_of_an_inactive_producer_show_only_with_figures(association):
    association.luis.status = association.luis.Status.INACTIVE
    association.luis.save()
    harvest(association.rio, date(2026, 2, 1), "1.0")

    farms = [row["farm"] for row in generate(association.admin, type="production", **PERIOD).rows]

    assert "F01 · Villa Luz" not in farms


def test_the_quality_report_adds_the_whole_discards(association):
    classify(association.rio, "80.0", "15.0", "5.0", at(2026, 1, 10, 9))
    lot = LotFactory(harvest__plot=association.alto, status=LotStatus.DISCARDED)
    dry(lot, "50.0")
    LotDiscardFactory(lot=lot, discarded_at=at(2026, 1, 11, 9))

    report = generate(association.admin, type="quality", **PERIOD)

    assert [column.key for column in report.columns][3:] == [
        "lots_classified",
        "lots_discarded",
        "classified_kg",
        "g1_kg",
        "g2_kg",
        "discard_kg",
        "g1_pct",
        "g2_pct",
        "discard_pct",
    ]
    first, second, zero = report.rows
    assert (first["farm"], first["classified_kg"], first["discard_pct"]) == (
        "F01 · La Esperanza",
        Decimal("100.0"),
        Decimal("5.0"),
    )
    assert (second["lots_discarded"], second["discard_kg"]) == (1, Decimal("50.0"))
    assert (zero["classified_kg"], zero["g1_pct"]) == (Decimal("0.0"), None)
    assert totals(report)["discard_kg"] == Decimal("55.0")


def test_the_sales_report_has_only_kg_and_no_money(association):
    sale_with_lines(
        association.esperanza,
        sale_date=date(2026, 2, 1),
        lines=(("g1", "100.0", 18500), ("g2", "20.0", 15000)),
    )
    sale_with_lines(association.esperanza, sale_date=date(2026, 2, 2), voided=True)

    report = generate(association.admin, type="sales", **PERIOD)

    assert [column.key for column in report.columns][3:] == ["g1_kg", "g2_kg", "sold_kg"]
    assert report.rows[0]["sold_kg"] == Decimal("120.0")
    assert totals(report)["sales"] == 1


@pytest.mark.parametrize("report_type", ["production", "quality", "sales"])
def test_nothing_by_plot_lot_stock_or_money_in_any_report(association, report_type):
    harvest(association.rio, date(2026, 2, 1), "1.0")
    classify(association.rio, "1.0", "0", "0", at(2026, 2, 1, 9))
    sale_with_lines(association.esperanza, sale_date=date(2026, 2, 1))

    report = generate(association.admin, type=report_type, **PERIOD)
    keys = [column.key for column in report.columns] + [total.key for total in report.totals]

    # Por palabra: contar lotes clasificados (`lots_classified`) no es mostrar un lote.
    assert not [key for key in keys if set(key.split("_")) & set(FORBIDDEN_KEYS)]


def test_the_figures_are_the_same_as_the_association_panel(association):
    dry(LotFactory(harvest=harvest(association.rio, date(2026, 2, 1), "100.0")), "35.0")
    harvest(association.alto, date(2026, 3, 1), "300.0")
    classify(association.rio, "80.0", "15.0", "5.0", at(2026, 1, 10, 9))
    sale_with_lines(association.mirador, sale_date=date(2026, 2, 1))
    panel = association_indicators(
        association.admin, IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))
    )["totals"]

    production = totals(generate(association.admin, type="production", **PERIOD))
    quality = totals(generate(association.admin, type="quality", **PERIOD))
    sales = totals(generate(association.admin, type="sales", **PERIOD))

    assert (production["green_kg"], production["dry_kg"]) == (panel["green_kg"], panel["dry_kg"])
    assert (quality["g1_pct"], quality["discard_pct"]) == (panel["g1_pct"], panel["discard_pct"])
    assert sales["sold_kg"] == panel["sold_kg"]


def test_the_filters_narrow_and_are_named(association):
    harvest(association.rio, date(2026, 2, 1), "1.0")

    by_municipality = generate(
        association.admin, type="production", **PERIOD, municipality="54001"
    )
    by_producer = generate(
        association.admin, type="production", **PERIOD, producer=str(association.rosa.pk)
    )
    by_farm = generate(
        association.admin,
        type="production",
        **PERIOD,
        producer=str(association.rosa.pk),
        farm=str(association.mirador.pk),
    )

    assert {row["farm"] for row in by_municipality.rows} == {
        "F01 · La Esperanza",
        "F01 · Villa Luz",
    }
    assert {row["farm"] for row in by_producer.rows} == {"F01 · La Esperanza", "F02 · El Mirador"}
    assert by_municipality.filters[1] == ReportFilter(
        "municipality", "Municipio", "Cúcuta", id="54001"
    )
    assert [item.key for item in by_farm.filters] == ["period", "producer", "farm"]
    assert by_farm.filters[2].text == "F02 · El Mirador"


def test_a_farm_of_another_producer_or_a_missing_producer_is_not_found(association):
    with pytest.raises(ReportFilterNotFound) as farm_error:
        generate(
            association.admin,
            type="production",
            **PERIOD,
            producer=str(association.rosa.pk),
            farm=str(association.villa_luz.pk),
        )
    with pytest.raises(ReportFilterNotFound) as producer_error:
        generate(association.admin, type="production", **PERIOD, producer=str(uuid.uuid4()))

    assert set(farm_error.value.fields) == {"farm"}
    assert set(producer_error.value.fields) == {"producer"}
