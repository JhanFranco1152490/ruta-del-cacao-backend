from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin, full_name

from .fields import (
    DAYS,
    FIELDS,
    HOURS,
    LIMITS,
    MAX_DAYS,
    MAX_WINDOW_HOURS,
    PERCENT,
    PERCENT_DECIMAL_PLACES,
    PERCENT_MAX_DIGITS,
    PH,
    PH_DECIMAL_PLACES,
    PH_MAX_DIGITS,
    POSITIVE_FIELDS,
    RANGE_PAIRS,
    TEMPERATURE,
    TEMPERATURE_DECIMAL_PLACES,
    TEMPERATURE_MAX_DIGITS,
    TURN_HOURS,
)

PERCENT_RANGE = "Debe estar entre 0 % y 100 %."
# Los validadores de mínimo y máximo arman su mensaje con `%`: el signo de porcentaje va doble.
PERCENT_RANGE_FOR_VALIDATOR = PERCENT_RANGE.replace("%", "%%")
WHOLE_POSITIVE = "Debe ser un número entero mayor que cero."
CAP_MESSAGES = {
    DAYS: f"Revisa la cifra: un secado no pasa de {MAX_DAYS} días.",
    HOURS: f"Revisa la cifra: la ventana no pasa de {MAX_WINDOW_HOURS} horas.",
    TURN_HOURS: f"Revisa la cifra: un volteo no se espera pasadas {MAX_WINDOW_HOURS} horas.",
}
TEMPERATURE_RANGE = "Debe estar entre 0 °C y 80 °C."
PH_RANGE = "Debe estar entre 0 y 14."
MIN_ABOVE_MAX = "El mínimo no puede ser mayor que el máximo"


# De cada tipo decimal: cuántos dígitos y decimales lleva y, para validar, qué dice al salirse.
DECIMAL_SPECS = {
    PERCENT: (PERCENT_MAX_DIGITS, PERCENT_DECIMAL_PLACES, PERCENT_RANGE, "Usa máximo 1 decimal."),
    TEMPERATURE: (
        TEMPERATURE_MAX_DIGITS,
        TEMPERATURE_DECIMAL_PLACES,
        TEMPERATURE_RANGE,
        "Usa máximo 1 decimal.",
    ),
    PH: (PH_MAX_DIGITS, PH_DECIMAL_PLACES, PH_RANGE, "Usa máximo 2 decimales."),
}


def _value_field(kind: str) -> serializers.Field:
    if kind in DECIMAL_SPECS:
        digits, places, _, _ = DECIMAL_SPECS[kind]
        return serializers.DecimalField(max_digits=digits, decimal_places=places)
    return serializers.IntegerField()


def _input_field(name: str, kind: str) -> serializers.Field:
    low, high = LIMITS[kind]
    if kind in DECIMAL_SPECS:
        digits, places, out_of_range, too_precise = DECIMAL_SPECS[kind]
        positive = name in POSITIVE_FIELDS
        # Los validadores de mínimo y máximo arman su mensaje con `%`: el signo va doble.
        escaped = out_of_range.replace("%", "%%")
        return serializers.DecimalField(
            max_digits=digits,
            decimal_places=places,
            # Con un decimal, lo más chico que pasa de cero es 0,1.
            min_value=Decimal("0.1") if positive else low,
            max_value=high,
            error_messages={
                "min_value": "Debe ser mayor que cero." if positive else escaped,
                "max_value": escaped,
                # 1000,0 no cabe en los dígitos antes de llegar a compararse con 100.
                "max_whole_digits": out_of_range,
                "max_digits": out_of_range,
                "max_decimal_places": too_precise,
            },
        )
    return serializers.IntegerField(
        min_value=low,
        max_value=high,
        error_messages={
            "invalid": WHOLE_POSITIVE,
            "min_value": WHOLE_POSITIVE,
            "max_value": CAP_MESSAGES[kind],
        },
    )


def _validate_ranges(self, attrs):
    # El error va en el mínimo: es el que se escribe primero y el que suele estar mal.
    errors = {low: [MIN_ABOVE_MAX] for low, high in RANGE_PAIRS if attrs[low] > attrs[high]}
    if errors:
        raise serializers.ValidationError(errors)
    return attrs


# Los veintiún parámetros, en el orden de la lista única. Se arman desde ella para que agregar uno
# no obligue a tocar la API.
PostharvestValuesSerializer = type(
    "PostharvestValuesSerializer",
    (serializers.Serializer,),
    {name: _value_field(kind) for name, kind in FIELDS.items()},
)

PostharvestValuesInputSerializer = type(
    "PostharvestValuesInputSerializer",
    (RejectUnknownFieldsMixin, serializers.Serializer),
    {
        **{name: _input_field(name, kind) for name, kind in FIELDS.items()},
        "validate": _validate_ranges,
    },
)


class ParametersAuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, account) -> str:
        return full_name(account)


class PostharvestParametersSerializer(serializers.Serializer):
    producer_id = serializers.UUIDField()
    # Verdadero si el productor no tiene parámetros guardados: `values` es entonces la línea base.
    is_default = serializers.BooleanField()
    values = PostharvestValuesSerializer()
    # Viaja siempre, para que el cliente no tenga su propia copia de la línea base.
    baseline = PostharvestValuesSerializer()
    # 0 mientras el productor use la línea base.
    version = serializers.IntegerField()
    updated_at = serializers.DateTimeField(allow_null=True)
    updated_by = ParametersAuthorSerializer(allow_null=True)


class PostharvestParametersResetSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Solo la cuenta técnica, y para ella obligatorio; en otra cuenta se ignora.
    producer = serializers.UUIDField(required=False)
    # 0 si el productor todavía usa la línea base.
    expected_version = serializers.IntegerField(min_value=0)


class PostharvestParametersSaveSerializer(PostharvestParametersResetSerializer):
    values = PostharvestValuesInputSerializer()


class ProducerQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)
