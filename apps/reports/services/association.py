"""Los reportes de la asociación: una fila por finca de los productores, con las mismas cifras que
el panel de la asociación, y nada por parcela, por lote, de existencias ni en pesos.

Esas cosas no se calculan, no solo no se muestran: cada tipo pide solo las fuentes agregadas por
finca de los indicadores que necesita.
"""

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

from django.utils import timezone

from apps.common.contracts.indicators import IndicatorPeriod, indicator_source
from apps.common.farm_figures import FarmFigures, figures_by_farm
from apps.common.figures import one_decimal, percentage
from apps.common.serializers import full_name
from apps.common.territorial import get_municipality

from ..exceptions import ReportFilterNotFound
from ..report import COUNT, KG, PCT, TEXT, Column, Report, ReportFilter, Total
from ..rules import labeled, period_text, producer_text
from ..types import PRODUCTION, QUALITY, SALES, TITLES


@dataclass(frozen=True)
class Measure:
    """Una cifra de la finca: su columna y cómo sale de sus `FarmFigures`. El total aplica la misma
    cuenta a la suma de las fincas, así que un porcentaje total sale de los kg sumados."""

    key: str
    label: str
    kind: str
    value: Callable[[FarmFigures], Any]


def _classified(farm: FarmFigures):
    return farm.g1_kg + farm.g2_kg + farm.discard_kg


MEASURES = {
    PRODUCTION: (
        Measure("green_kg", "Kg en baba", KG, lambda farm: one_decimal(farm.green_kg)),
        Measure("dry_kg", "Kg seco", KG, lambda farm: one_decimal(farm.dry_kg)),
        Measure(
            "green_kg_not_dried",
            "Kg en baba sin secar",
            KG,
            lambda farm: one_decimal(farm.green_kg_not_dried),
        ),
    ),
    QUALITY: (
        Measure("lots_classified", "Lotes clasificados", COUNT, lambda f: f.lots_classified),
        Measure("lots_discarded", "Lotes descartados", COUNT, lambda f: f.lots_discarded),
        Measure("classified_kg", "Kg clasificados", KG, lambda f: one_decimal(_classified(f))),
        Measure("g1_kg", "Kg G1", KG, lambda farm: one_decimal(farm.g1_kg)),
        Measure("g2_kg", "Kg G2", KG, lambda farm: one_decimal(farm.g2_kg)),
        Measure("discard_kg", "Kg descarte", KG, lambda farm: one_decimal(farm.discard_kg)),
        Measure("g1_pct", "% G1", PCT, lambda f: percentage(f.g1_kg, _classified(f))),
        Measure("g2_pct", "% G2", PCT, lambda f: percentage(f.g2_kg, _classified(f))),
        Measure(
            "discard_pct", "% descarte", PCT, lambda f: percentage(f.discard_kg, _classified(f))
        ),
    ),
    SALES: (
        Measure("g1_kg", "Kg G1 vendidos", KG, lambda farm: one_decimal(farm.sold_g1_kg)),
        Measure("g2_kg", "Kg G2 vendidos", KG, lambda farm: one_decimal(farm.sold_g2_kg)),
        Measure("sold_kg", "Kg vendidos", KG, lambda farm: one_decimal(farm.sold_kg)),
    ),
}

# La cifra que ordena las fincas, de más a menos.
MAIN_MEASURE = {PRODUCTION: "green_kg", QUALITY: "classified_kg", SALES: "sold_kg"}

# Qué fuentes pide cada tipo, con el nombre del argumento de `figures_by_farm`.
SOURCES = {
    PRODUCTION: {"harvests": "harvested", "drying": "dried"},
    QUALITY: {"quality": "quality"},
    SALES: {"sales": "sales"},
}

FARM_COLUMNS = (
    Column("farm", "Finca", TEXT),
    Column("municipality", "Municipio", TEXT),
    Column("producer", "Productor", TEXT),
)


def association_report(actor, query: dict) -> Report:
    report_type = query["type"]
    period = IndicatorPeriod(query["from"], query["to"])
    filters = [ReportFilter("period", "Periodo", period_text(period))]
    municipality = query.get("municipality")
    if municipality is not None:
        name = get_municipality(municipality).name
        filters.append(ReportFilter("municipality", "Municipio", name, id=municipality))
    producer_id = query.get("producer")
    if producer_id is not None:
        filters.append(_producer_filter(actor, producer_id))
    farm_id = query.get("farm")
    farm_ids = indicator_source("farm_scope")(
        actor,
        everyone=True,
        producer_id=producer_id,
        farm_id=farm_id,
        municipality_code=municipality,
    )
    farms = indicator_source("farms")(farm_ids)
    if farm_id is not None:
        if not farms:
            raise ReportFilterNotFound("farm")
        name = labeled(farms[0].code, farms[0].name)
        filters.append(ReportFilter("farm", "Finca", name, id=farm_id))
    measures = MEASURES[report_type]
    figures = _figures(report_type, farm_ids, period)
    shown = _shown_farms(farms, figures, measures, MAIN_MEASURE[report_type])
    return Report(
        type=report_type,
        title=TITLES[report_type],
        generated_at=timezone.now(),
        generated_by=full_name(actor),
        filters=tuple(filters),
        columns=FARM_COLUMNS + tuple(Column(m.key, m.label, m.kind) for m in measures),
        rows=[_row(farm, figures.get(farm.farm_id, FarmFigures()), measures) for farm in shown],
        totals=_totals(report_type, shown, figures, measures),
    )


def _producer_filter(actor, producer_id) -> ReportFilter:
    # El productor se nombra por sus fincas: uno sin ninguna no tiene nada que reportar.
    farm_ids = indicator_source("farm_scope")(actor, everyone=True, producer_id=producer_id)
    farms = indicator_source("farms")(farm_ids)
    if not farms:
        raise ReportFilterNotFound("producer")
    farm = farms[0]
    text = producer_text(
        farm.producer_member_code, farm.producer_first_name, farm.producer_last_name
    )
    return ReportFilter("producer", "Productor", text, id=producer_id)


def _figures(report_type, farm_ids, period) -> dict:
    rows = {"harvested": [], "dried": [], "quality": [], "sales": []}
    for source, argument in SOURCES[report_type].items():
        rows[argument] = indicator_source(source)(farm_ids, period)
    return figures_by_farm(**rows)


def _shown_farms(farms, figures: dict, measures, main_key: str) -> list:
    """Todas las fincas, también en 0 (el reporte es para el seguimiento), salvo las inactivas o de
    productores inactivos, que solo salen con cifras. Sin ninguna cifra no hay reporte: una tabla
    de ceros no lo es."""
    if not figures:
        return []
    main = next(measure for measure in measures if measure.key == main_key)
    shown = [
        farm
        for farm in farms
        if (farm.is_active and farm.producer_is_active) or farm.farm_id in figures
    ]
    shown.sort(key=lambda farm: (-main.value(figures.get(farm.farm_id, FarmFigures())), farm.name))
    return shown


def _row(farm, figures: FarmFigures, measures) -> dict:
    return {
        "farm": labeled(farm.code, farm.name),
        "municipality": get_municipality(farm.municipality_code).name,
        "producer": producer_text(
            farm.producer_member_code, farm.producer_first_name, farm.producer_last_name
        ),
        **{measure.key: measure.value(figures) for measure in measures},
    }


def _totals(report_type, shown, figures: dict, measures) -> tuple[Total, ...]:
    total = _sum(figures.get(farm.farm_id, FarmFigures()) for farm in shown)
    extra = ()
    if report_type == PRODUCTION:
        extra = (
            Total("producers", "Productores", COUNT, len({farm.producer_id for farm in shown})),
            Total("farms", "Fincas", COUNT, len(shown)),
        )
    elif report_type == SALES:
        extra = (Total("sales", "Ventas", COUNT, total.sales),)
    return extra + tuple(
        Total(measure.key, measure.label, measure.kind, measure.value(total))
        for measure in measures
    )


def _sum(items) -> FarmFigures:
    totals = {field.name: field.default for field in fields(FarmFigures)}
    for item in items:
        for name in totals:
            totals[name] += getattr(item, name)
    return FarmFigures(**totals)
