"""El secado en la historia de un lote: una sola etapa, con su bitácora resumida y en lista, y lo
que dio al finalizar."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.common.contracts.lot_history import LotHistoryStage, stage_days
from apps.common.serializers import full_name

from .models import ONE_DECIMAL, DryingProcess, Weather


@dataclass(frozen=True)
class DryingLogData:
    day_number: int
    log_date: date
    moisture_pct: Decimal
    sun_hours: Decimal
    weather: str


@dataclass(frozen=True)
class DryingData:
    started_at: datetime
    # El fin y el resultado son nulos mientras seca.
    ended_at: datetime | None
    days: int
    facility: str
    responsible: str
    entry_moisture_pct: Decimal
    log_count: int
    # La humedad del último registro de la bitácora; sin registros, nula.
    last_moisture_pct: Decimal | None
    total_sun_hours: Decimal
    final_moisture_pct: Decimal | None
    dry_weight_kg: Decimal | None
    yield_pct: Decimal | None
    logs: tuple[DryingLogData, ...]


def log_summary(logs: tuple[DryingLogData, ...], *, stored_sun_hours: Decimal | None) -> dict:
    """Cuántos días se registraron, la última humedad medida y las horas de sol. Un secado
    finalizado ya guardó sus horas de sol; uno en curso suma las de su bitácora."""
    sun_hours = stored_sun_hours
    if sun_hours is None:
        sun_hours = sum((log.sun_hours for log in logs), Decimal("0.0"))
    return {
        "log_count": len(logs),
        "last_moisture_pct": logs[-1].moisture_pct if logs else None,
        "total_sun_hours": sun_hours,
    }


def drying_history(lot_id) -> list[LotHistoryStage]:
    process = (
        DryingProcess.objects.filter(lot_id=lot_id)
        .select_related("facility", "responsible")
        .prefetch_related("logs")
        .first()
    )
    if process is None:
        return []
    logs = tuple(
        DryingLogData(
            day_number=log.day_number,
            log_date=log.log_date,
            moisture_pct=log.moisture_pct,
            sun_hours=log.sun_hours,
            weather=log.weather,
        )
        for log in sorted(process.logs.all(), key=lambda log: log.day_number)
    )
    data = DryingData(
        started_at=process.started_at,
        ended_at=process.ended_at,
        days=stage_days(process.started_at, process.ended_at, today=timezone.localdate()),
        facility=process.facility.name,
        responsible=full_name(process.responsible),
        entry_moisture_pct=process.entry_moisture_pct,
        final_moisture_pct=process.final_moisture_pct,
        dry_weight_kg=process.dry_weight_kg,
        yield_pct=process.yield_pct,
        logs=logs,
        **log_summary(logs, stored_sun_hours=process.total_sun_hours),
    )
    return [
        LotHistoryStage.at("drying", process.started_at, recorded_at=process.created_at, data=data)
    ]


def _decimal(max_digits, **kwargs):
    return serializers.DecimalField(max_digits=max_digits, decimal_places=ONE_DECIMAL, **kwargs)


class DryingLogStageSerializer(serializers.Serializer):
    day_number = serializers.IntegerField()
    log_date = serializers.DateField()
    moisture_pct = _decimal(4)
    sun_hours = _decimal(3)
    weather = serializers.ChoiceField(choices=Weather.choices)


class DryingStageSerializer(serializers.Serializer):
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    days = serializers.IntegerField()
    facility = serializers.CharField()
    responsible = serializers.CharField()
    entry_moisture_pct = _decimal(4)
    log_count = serializers.IntegerField()
    last_moisture_pct = _decimal(4, allow_null=True)
    total_sun_hours = _decimal(5)
    final_moisture_pct = _decimal(4, allow_null=True)
    dry_weight_kg = _decimal(7, allow_null=True)
    yield_pct = _decimal(4, allow_null=True)
    logs = DryingLogStageSerializer(many=True)
