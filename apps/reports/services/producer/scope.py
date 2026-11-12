"""Qué alcanza un reporte del productor: las fincas, el periodo, la parcela y el lote, con los
filtros nombrados como se muestran.

Aquí se decide todo lo que puede negar el reporte (el permiso del módulo y los filtros que no
existen o no están en el alcance), antes de leer una sola fila.
"""

from dataclasses import dataclass
from typing import Any

from apps.common.contracts.indicators import IndicatorPeriod, indicator_source
from apps.common.contracts.reports import report_source

from ...exceptions import ReportFilterNotFound, ReportTypeNotAllowed
from ...report import ReportFilter
from ...rules import labeled, period_text, producer_text
from ...types import MODULE_PERMISSIONS


@dataclass(frozen=True)
class ProducerScope:
    farm_ids: Any
    period: IndicatorPeriod | None
    plot_id: Any
    lot_id: Any
    filters: tuple[ReportFilter, ...]


def resolve_scope(actor, query: dict) -> ProducerScope:
    if not actor.has_perm(MODULE_PERMISSIONS[query["type"]]):
        raise ReportTypeNotAllowed()
    farm_id = query.get("farm")
    # Solo la cuenta técnica elige productor; las demás ven lo suyo, como en las listas.
    producer_id = query.get("producer") if actor.is_superuser else None
    farm_ids = indicator_source("farm_scope")(actor, farm_id=farm_id, producer_id=producer_id)
    filters = []
    period = None
    if "from" in query:
        period = IndicatorPeriod(query["from"], query["to"])
        filters.append(ReportFilter("period", "Periodo", period_text(period)))
    if producer_id is not None:
        filters.append(_producer_filter(farm_ids, producer_id))
    if farm_id is not None:
        filters.append(_farm_filter(farm_ids, farm_id))
    plot_id = query.get("plot")
    if plot_id is not None:
        filters.append(_plot_filter(farm_ids, plot_id))
    lot_id = query.get("lot")
    if lot_id is not None:
        filters.append(_lot_filter(farm_ids, lot_id, plot_id))
    return ProducerScope(farm_ids, period, plot_id, lot_id, tuple(filters))


def _producer_filter(farm_ids, producer_id) -> ReportFilter:
    # El productor se nombra por sus fincas: uno sin ninguna no tiene nada que reportar.
    farms = indicator_source("farms")(farm_ids)
    if not farms:
        raise ReportFilterNotFound("producer")
    farm = farms[0]
    text = producer_text(
        farm.producer_member_code, farm.producer_first_name, farm.producer_last_name
    )
    return ReportFilter("producer", "Productor", text, id=producer_id)


def _farm_filter(farm_ids, farm_id) -> ReportFilter:
    # `farm_ids` ya viene acotado a esa finca: vacío si no existe o no está en el alcance.
    farms = indicator_source("farms")(farm_ids)
    if not farms:
        raise ReportFilterNotFound("farm")
    return ReportFilter("farm", "Finca", labeled(farms[0].code, farms[0].name), id=farm_id)


def _plot_filter(farm_ids, plot_id) -> ReportFilter:
    plot = report_source("plot_in_scope")(farm_ids, plot_id)
    if plot is None:
        raise ReportFilterNotFound("plot")
    return ReportFilter("plot", "Parcela", labeled(plot.code, plot.name), id=plot_id)


def _lot_filter(farm_ids, lot_id, plot_id) -> ReportFilter:
    lot = report_source("lot_in_scope")(farm_ids, lot_id)
    if lot is None or (plot_id is not None and lot.plot_id != plot_id):
        raise ReportFilterNotFound("lot")
    return ReportFilter("lot", "Lote", lot.code, id=lot_id)
