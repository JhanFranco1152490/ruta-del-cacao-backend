"""La fermentación en la historia de un lote: una sola etapa, con sus volteos resumidos y en
lista."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.common.contracts.lot_history import LotHistoryStage, stage_days
from apps.common.serializers import full_name

from .models import PH_DECIMAL_PLACES, TEMPERATURE_DECIMAL_PLACES, FermentationProcess


@dataclass(frozen=True)
class FermentationTurnData:
    turned_at: datetime
    temperature_c: Decimal
    ph: Decimal


@dataclass(frozen=True)
class FermentationData:
    started_at: datetime
    # Sin fin mientras fermenta.
    ended_at: datetime | None
    days: int
    facility: str
    responsible: str
    turn_count: int
    # Sin volteos no hay extremos ni último volteo.
    temperature_min_c: Decimal | None
    temperature_max_c: Decimal | None
    ph_min: Decimal | None
    ph_max: Decimal | None
    last_turn_at: datetime | None
    turns: tuple[FermentationTurnData, ...]


def turn_summary(turns: tuple[FermentationTurnData, ...]) -> dict:
    """Cuántos volteos hubo, los extremos de temperatura y pH, y cuándo fue el último."""
    if not turns:
        return {
            "turn_count": 0,
            "temperature_min_c": None,
            "temperature_max_c": None,
            "ph_min": None,
            "ph_max": None,
            "last_turn_at": None,
        }
    temperatures = [turn.temperature_c for turn in turns]
    phs = [turn.ph for turn in turns]
    return {
        "turn_count": len(turns),
        "temperature_min_c": min(temperatures),
        "temperature_max_c": max(temperatures),
        "ph_min": min(phs),
        "ph_max": max(phs),
        "last_turn_at": max(turn.turned_at for turn in turns),
    }


def fermentation_history(lot_id) -> list[LotHistoryStage]:
    process = (
        FermentationProcess.objects.filter(lot_id=lot_id)
        .select_related("facility", "responsible")
        .prefetch_related("turns")
        .first()
    )
    if process is None:
        return []
    turns = tuple(
        FermentationTurnData(
            turned_at=turn.turned_at, temperature_c=turn.temperature_c, ph=turn.ph
        )
        for turn in sorted(process.turns.all(), key=lambda turn: turn.turned_at)
    )
    data = FermentationData(
        started_at=process.started_at,
        ended_at=process.ended_at,
        days=stage_days(process.started_at, process.ended_at, today=timezone.localdate()),
        facility=process.facility.name,
        responsible=full_name(process.responsible),
        turns=turns,
        **turn_summary(turns),
    )
    return [
        LotHistoryStage.at(
            "fermentation", process.started_at, recorded_at=process.created_at, data=data
        )
    ]


def _temperature(**kwargs):
    return serializers.DecimalField(
        max_digits=3, decimal_places=TEMPERATURE_DECIMAL_PLACES, **kwargs
    )


def _ph(**kwargs):
    return serializers.DecimalField(max_digits=4, decimal_places=PH_DECIMAL_PLACES, **kwargs)


class FermentationTurnStageSerializer(serializers.Serializer):
    turned_at = serializers.DateTimeField()
    temperature_c = _temperature()
    ph = _ph()


class FermentationStageSerializer(serializers.Serializer):
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    days = serializers.IntegerField()
    facility = serializers.CharField()
    responsible = serializers.CharField()
    turn_count = serializers.IntegerField()
    temperature_min_c = _temperature(allow_null=True)
    temperature_max_c = _temperature(allow_null=True)
    ph_min = _ph(allow_null=True)
    ph_max = _ph(allow_null=True)
    last_turn_at = serializers.DateTimeField(allow_null=True)
    turns = FermentationTurnStageSerializer(many=True)
