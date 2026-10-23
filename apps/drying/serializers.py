from dataclasses import asdict

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.common.contracts.harvest_representation import (
    HarvestRecorderSerializer,
    HarvestRepresentationSerializer,
)
from apps.common.contracts.postharvest_parameters import drying_parameters
from apps.common.hours import hours_between
from apps.common.serializers import full_name

from .models import ONE_DECIMAL, DryingProcess, Weather
from .rules import day_number

# Las opciones del estado del lote se toman de su campo por la relación, sin importar su app: así
# el esquema las reconoce como el mismo enum de los lotes.
LOT_STATUS_CHOICES = (
    DryingProcess._meta.get_field("lot").related_model._meta.get_field("status").choices
)


def _decimal(max_digits, **kwargs):
    return serializers.DecimalField(max_digits=max_digits, decimal_places=ONE_DECIMAL, **kwargs)


class DryingLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LOT_STATUS_CHOICES)
    green_weight_kg = _decimal(7, source="harvest.green_weight_kg")
    # El origen que muestra la ficha del lote, para que la copia sin conexión la arme sola.
    harvest = HarvestRepresentationSerializer()


class DryingFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class DryingDryerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    capacity_kg = _decimal(6)


class DryingPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()


class DryingRangeSerializer(serializers.Serializer):
    min = _decimal(4)
    max = _decimal(4)


class DryingDaysSerializer(serializers.Serializer):
    min = serializers.IntegerField()
    max = serializers.IntegerField()


class DryingLogSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    measured_at = serializers.DateTimeField()
    log_date = serializers.DateField()
    day_number = serializers.IntegerField()
    moisture_pct = _decimal(4)
    sun_hours = _decimal(3)
    shade_hours = _decimal(3, allow_null=True)
    turn_count = serializers.IntegerField()
    turn_frequency_hours = _decimal(3, allow_null=True)
    weather = serializers.ChoiceField(choices=Weather.choices)
    notes = serializers.CharField()
    recorded_by = serializers.SerializerMethodField()
    version = serializers.IntegerField()

    @extend_schema_field(HarvestRecorderSerializer)
    def get_recorded_by(self, entry):
        account = entry.recorded_by
        return HarvestRecorderSerializer({"id": account.pk, "full_name": full_name(account)}).data


class DryingResultSerializer(serializers.Serializer):
    ended_at = serializers.DateTimeField()
    duration_hours = _decimal(6)
    days = serializers.IntegerField()
    total_sun_hours = _decimal(5)
    final_moisture_pct = _decimal(4)
    dry_weight_kg = _decimal(7)
    yield_pct = _decimal(4)


class DryingProcessSerializer(serializers.Serializer):
    lot = DryingLotSerializer()
    farm = DryingFarmSerializer(source="lot.harvest.plot.farm")
    facility = DryingDryerSerializer()
    started_at = serializers.DateTimeField()
    entry_moisture_pct = _decimal(4)
    entry_moisture_out_of_range = serializers.BooleanField()
    responsible = serializers.SerializerMethodField()
    estimated_days = serializers.SerializerMethodField()
    target_moisture = serializers.SerializerMethodField()
    current_day = serializers.SerializerMethodField()
    elapsed_hours = serializers.SerializerMethodField()
    logs = DryingLogSerializer(many=True)
    result = serializers.SerializerMethodField()
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def _now(self):
        # Un solo "ahora" por respuesta: todos los secados de una lista se cuentan igual.
        if "now" not in self.context:
            self.context["now"] = timezone.now()
        return self.context["now"]

    def _parameters(self, process):
        # Una lectura por productor, aunque la lista tenga muchos secados suyos.
        cache = self.context.setdefault("parameters", {})
        producer_id = process.lot.harvest.plot.farm.producer_id
        if producer_id not in cache:
            cache[producer_id] = asdict(drying_parameters(producer_id))
        return cache[producer_id]

    def _end(self, process):
        return process.ended_at or self._now()

    @extend_schema_field(DryingPersonSerializer)
    def get_responsible(self, process):
        account = process.responsible
        return DryingPersonSerializer(
            {"id": account.pk, "full_name": full_name(account), "is_active": account.is_active}
        ).data

    @extend_schema_field(DryingDaysSerializer)
    def get_estimated_days(self, process):
        parameters = self._parameters(process)
        return {"min": parameters["estimated_days_min"], "max": parameters["estimated_days_max"]}

    @extend_schema_field(DryingRangeSerializer)
    def get_target_moisture(self, process):
        parameters = self._parameters(process)
        return DryingRangeSerializer(
            {
                "min": parameters["target_moisture_min_pct"],
                "max": parameters["target_moisture_max_pct"],
            }
        ).data

    @extend_schema_field(serializers.IntegerField())
    def get_current_day(self, process):
        return day_number(timezone.localdate(self._end(process)), process.started_at)

    @extend_schema_field(_decimal(6))
    def get_elapsed_hours(self, process):
        return f"{hours_between(process.started_at, self._end(process)):.1f}"

    @extend_schema_field(DryingResultSerializer(allow_null=True))
    def get_result(self, process):
        if process.ended_at is None:
            return None
        return DryingResultSerializer(
            {
                "ended_at": process.ended_at,
                "duration_hours": hours_between(process.started_at, process.ended_at),
                "days": day_number(timezone.localdate(process.ended_at), process.started_at),
                "total_sun_hours": process.total_sun_hours,
                "final_moisture_pct": process.final_moisture_pct,
                "dry_weight_kg": process.dry_weight_kg,
                "yield_pct": process.yield_pct,
            }
        ).data


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class DryingListSerializer(serializers.Serializer):
    results = DryingProcessSerializer(many=True)


class DryingListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField(required=False)
    producer = serializers.UUIDField(required=False)
