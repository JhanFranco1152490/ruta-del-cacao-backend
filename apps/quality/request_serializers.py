"""Lo que reciben las escrituras de calidad."""

from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin

from .models import MAX_PERCENT, NOTES_MAX_LENGTH, ONE_DECIMAL
from .serializers import LotQualitySerializer

PERCENT_MESSAGE = "El valor debe estar entre 0 y 100"
PERCENTAGES = ("well_fermented_pct", "moldy_pct", "other_defects_pct")


def percent_input(**kwargs):
    # Un dígito más de los que guarda la base: así 100,1 llega a la regla y responde su rango, en
    # vez de un error de cantidad de dígitos.
    return serializers.DecimalField(
        max_digits=5, decimal_places=ONE_DECIMAL, validators=[_check_percent], **kwargs
    )


def _check_percent(value):
    if not 0 <= value <= MAX_PERCENT:
        raise serializers.ValidationError(PERCENT_MESSAGE)


class EvaluationCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # La versión del lote que se leyó: si otra persona lo cambió, no se evalúa a ciegas.
    expected_lot_version = serializers.IntegerField(min_value=1)
    well_fermented_pct = percent_input()
    moldy_pct = percent_input()
    other_defects_pct = percent_input()
    notes = serializers.CharField(
        max_length=NOTES_MAX_LENGTH, allow_blank=True, required=False, default=""
    )


class EvaluationUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    well_fermented_pct = percent_input(required=False)
    moldy_pct = percent_input(required=False)
    other_defects_pct = percent_input(required=False)
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH, allow_blank=True, required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if not {*PERCENTAGES, "notes"} & set(attrs):
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class QualityConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y `current_status` con `lot_invalid_status`.
    current = LotQualitySerializer(required=False)
    current_status = serializers.CharField(required=False)


class QualitySumErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: `total_pct` llega con `quality_sum_exceeds_100`.
    total_pct = serializers.CharField(required=False)
