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
from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin, full_name

from .models import MAX_PERCENT, ONE_DECIMAL, DryingProcess, Weather
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


PERCENT_MESSAGE = "Debe estar entre 0 % y 100 %."


def percent_input(**kwargs):
    # Un dígito más de los que guarda la base: así 100,1 llega a la regla y responde su rango, en
    # vez de un error de cantidad de dígitos.
    return serializers.DecimalField(max_digits=5, decimal_places=ONE_DECIMAL, **kwargs)


def check_percent(value):
    if value is not None and not 0 <= value <= MAX_PERCENT:
        raise serializers.ValidationError(PERCENT_MESSAGE)
    return value


class DryingStartSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    lot_id = serializers.UUIDField()
    facility_id = serializers.UUIDField()
    started_at = serializers.DateTimeField()
    entry_moisture_pct = percent_input()
    responsible_id = serializers.UUIDField()
    # Que quien registra vio el aviso de que la humedad de entrada está fuera del rango esperado.
    confirm_entry_moisture = serializers.BooleanField(default=False)

    def validate_entry_moisture_pct(self, value):
        return check_percent(value)


class DryingStartUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    facility_id = serializers.UUIDField(required=False)
    started_at = serializers.DateTimeField(required=False)
    entry_moisture_pct = percent_input(required=False)
    responsible_id = serializers.UUIDField(required=False)
    confirm_entry_moisture = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)

    def validate_entry_moisture_pct(self, value):
        return check_percent(value)

    def validate(self, attrs):
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        # La confirmación sola no cambia nada.
        if not {"facility_id", "started_at", "entry_moisture_pct", "responsible_id"} & set(attrs):
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class DryingStartOptionsQuerySerializer(serializers.Serializer):
    lot = serializers.UUIDField()


class DryingStartOptionPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()
    assignable = serializers.BooleanField()


class DryingStartOptionsSerializer(serializers.Serializer):
    facilities = DryingDryerSerializer(many=True)
    responsibles = DryingStartOptionPersonSerializer(many=True)
    entry_moisture_range = DryingRangeSerializer()
    earliest_start_at = serializers.DateTimeField()


class DryingConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version`, y `current_status` con `lot_invalid_status`.
    current = DryingProcessSerializer(required=False)
    current_status = serializers.CharField(required=False)


class EntryMoistureErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: llega con `entry_moisture_out_of_range`.
    range = DryingRangeSerializer(required=False)


class DryingFinishSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    ended_at = serializers.DateTimeField()
    final_moisture_pct = percent_input()
    # Un dígito más de los que guarda la base, como el porcentaje: así un peso muy grande llega a
    # la regla del peso en verde en vez de un error de cantidad de dígitos.
    dry_weight_kg = serializers.DecimalField(max_digits=8, decimal_places=ONE_DECIMAL)

    def validate_final_moisture_pct(self, value):
        return check_percent(value)

    def validate_dry_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError("Debe ser mayor que cero.")
        return value


class DryWeightErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: llega cuando el peso seco pasa del peso en verde del lote.
    green_weight_kg = _decimal(7, required=False)
