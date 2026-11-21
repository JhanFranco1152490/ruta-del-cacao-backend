"""La trazabilidad pública de un lote: lo que ve cualquiera que escanea su QR, sin cuenta.

Se arma con las mismas etapas de la historia, pero se queda solo con fechas, el origen (finca,
municipio y variedad) y la calidad. Las personas, los kilos, las bodegas, las salidas y las ventas
no salen de aquí: el consumidor no debe ver precios, compradores ni datos personales.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.common.territorial import get_department, get_municipality

from ..exceptions import LotNotFound
from ..models import LotQrCode
from .history import build_lot_stages

# Sin ventas: no aportan nada público y así sus datos ni se leen.
PUBLIC_SOURCES = ("fermentation_history", "drying_history", "quality_history", "warehouse_history")
DATED_KINDS = ("harvest", "evaluation", "classification", "stock_entry")
SPAN_KINDS = ("fermentation", "drying")
TOKEN_FORMAT = re.compile(r"[A-Za-z0-9_-]{16}\Z")


@dataclass(frozen=True)
class PublicOrigin:
    farm: str
    municipality: str
    department: str
    variety: str


@dataclass(frozen=True)
class PublicDatedStage:
    kind: str
    date: date


@dataclass(frozen=True)
class PublicSpanStage:
    kind: str
    started_on: date
    # Nulo mientras la etapa sigue en curso.
    ended_on: date | None
    days: int


@dataclass(frozen=True)
class PublicQuality:
    well_fermented_pct: Decimal
    g1_pct: Decimal | None
    g2_pct: Decimal | None
    discard_pct: Decimal | None


@dataclass(frozen=True)
class PublicLotTraceability:
    origin: PublicOrigin
    stages: list[PublicDatedStage | PublicSpanStage]
    quality: PublicQuality


def _find_qr(token: str) -> LotQrCode:
    # Un token con otra forma no va a la base: no existe, y así nada raro llega a la consulta.
    if not isinstance(token, str) or not TOKEN_FORMAT.match(token):
        raise LotNotFound()
    qr = (
        LotQrCode.objects.select_related(
            "lot__harvest__plot__farm",
            "lot__harvest__variety",
            "lot__harvest__collector",
            "lot__created_by",
        )
        .filter(token=token)
        .first()
    )
    if qr is None:
        raise LotNotFound()
    return qr


def _origin(lot) -> PublicOrigin:
    farm = lot.harvest.plot.farm
    return PublicOrigin(
        farm=farm.name,
        municipality=get_municipality(farm.municipality_code).name,
        department=get_department(farm.department_code).name,
        variety=lot.harvest.variety.name,
    )


def _public_stage(stage):
    if stage.kind in DATED_KINDS:
        return PublicDatedStage(stage.kind, stage.occurred_on)
    span = stage.data
    ended_on = None if span.ended_at is None else timezone.localdate(span.ended_at)
    return PublicSpanStage(stage.kind, stage.occurred_on, ended_on, span.days)


def _quality(stages) -> PublicQuality:
    by_kind = {stage.kind: stage.data for stage in stages}
    evaluation, classification = by_kind["evaluation"], by_kind["classification"]
    return PublicQuality(
        well_fermented_pct=evaluation.well_fermented_pct,
        g1_pct=classification.g1_pct,
        g2_pct=classification.g2_pct,
        discard_pct=classification.discard_pct,
    )


def public_lot_traceability(token: str) -> PublicLotTraceability:
    """La trazabilidad pública del lote del QR `token`. Un token que no existe o no tiene la forma
    de uno responde lo mismo: no se encontró. No mira el estado del productor: un QR impreso sigue
    abriendo aunque el productor se desactive."""
    lot = _find_qr(token).lot
    stages = build_lot_stages(lot, sources=PUBLIC_SOURCES)
    public = [stage for stage in stages if stage.kind in DATED_KINDS + SPAN_KINDS]
    return PublicLotTraceability(
        origin=_origin(lot),
        stages=[_public_stage(stage) for stage in public],
        quality=_quality(public),
    )
