"""Lo que llega al registrar, corregir y eliminar una bitácora, y sus errores."""

from rest_framework import serializers

from apps.common.serializers import (
    ApiErrorSerializer,
    DeviationSerializer,
    RejectUnknownFieldsMixin,
)

from .models import (
    MAX_DAY_HOURS,
    MAX_TURNS_PER_DAY,
    MIN_TURN_FREQUENCY_HOURS,
    NOTES_MAX_LENGTH,
    ONE_DECIMAL,
    Weather,
)
from .serializers import DryingLogSerializer, check_percent, percent_input

DAY_HOURS_MESSAGE = "Debe estar entre 0 y 24 horas."
FREQUENCY_MESSAGE = "Debe estar entre 0,5 y 24 horas."


def day_hours_input(**kwargs):
    # Un dígito más de los que guarda la base, por la misma razón que el porcentaje.
    return serializers.DecimalField(max_digits=4, decimal_places=ONE_DECIMAL, **kwargs)


def check_day_hours(value):
    if value is not None and not 0 <= value <= MAX_DAY_HOURS:
        raise serializers.ValidationError(DAY_HOURS_MESSAGE)
    return value


class DryingLogContentMixin(serializers.Serializer):
    measured_at = serializers.DateTimeField()
    moisture_pct = percent_input()
    sun_hours = day_hours_input()
    shade_hours = day_hours_input(required=False, allow_null=True)
    turn_count = serializers.IntegerField(
        min_value=0,
        max_value=MAX_TURNS_PER_DAY,
        error_messages={
            "min_value": "No puede ser negativo.",
            "max_value": f"Revisa la cifra: no más de {MAX_TURNS_PER_DAY} volteos al día.",
        },
    )
    # Cada cuántas horas se volteó; sin volteos va vacía.
    turn_frequency_hours = day_hours_input(required=False, allow_null=True)
    weather = serializers.ChoiceField(choices=Weather.choices)
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH, allow_blank=True, required=False)

    def validate_moisture_pct(self, value):
        return check_percent(value)

    def validate_sun_hours(self, value):
        return check_day_hours(value)

    def validate_shade_hours(self, value):
        return check_day_hours(value)

    def validate_turn_frequency_hours(self, value):
        if value is not None and not MIN_TURN_FREQUENCY_HOURS <= value <= MAX_DAY_HOURS:
            raise serializers.ValidationError(FREQUENCY_MESSAGE)
        return value


class DryingLogCreateSerializer(RejectUnknownFieldsMixin, DryingLogContentMixin):
    # Lo genera el dispositivo, para que un reenvío desde la cola no cree otra bitácora.
    id = serializers.UUIDField()
    # La hora del dispositivo al guardar, informativa.
    captured_at = serializers.DateTimeField(required=False, allow_null=True)


class DryingLogUpdateSerializer(RejectUnknownFieldsMixin, DryingLogContentMixin):
    expected_version = serializers.IntegerField(min_value=1, required=False)

    def get_fields(self):
        fields = super().get_fields()
        for name in ("measured_at", "moisture_pct", "sun_hours", "turn_count", "weather"):
            fields[name].required = False
        return fields

    def validate(self, attrs):
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class DryingLogSavedSerializer(DryingLogSerializer):
    # Los desvíos de la bitácora recién guardada, para que quien la registró los vea en el
    # momento y no solo en la bandeja.
    alerts = DeviationSerializer(many=True)


class DryingLogDeleteSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class DuplicateDryingLogSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    day_number = serializers.IntegerField()


class DryingLogConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: `existing` llega con `duplicate_drying_log_date`, y `current` con
    # `stale_version`.
    existing = DuplicateDryingLogSerializer(required=False)
    current = DryingLogSerializer(required=False)


class DryingHoursErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: llega cuando las horas al sol y a la sombra pasan de las del día.
    available_hours = serializers.DecimalField(
        max_digits=4, decimal_places=ONE_DECIMAL, required=False
    )
