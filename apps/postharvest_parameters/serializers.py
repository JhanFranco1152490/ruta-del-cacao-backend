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
    POSITIVE_FIELDS,
    RANGE_PAIRS,
)

PERCENT_RANGE = "Debe estar entre 0 % y 100 %."
# Los validadores de mínimo y máximo arman su mensaje con `%`: el signo de porcentaje va doble.
PERCENT_RANGE_FOR_VALIDATOR = PERCENT_RANGE.replace("%", "%%")
WHOLE_POSITIVE = "Debe ser un número entero mayor que cero."
CAP_MESSAGES = {
    DAYS: f"Revisa la cifra: un secado no pasa de {MAX_DAYS} días.",
    HOURS: f"Revisa la cifra: la ventana no pasa de {MAX_WINDOW_HOURS} horas.",
}
MIN_ABOVE_MAX = "El mínimo no puede ser mayor que el máximo"


def _value_field(kind: str) -> serializers.Field:
    if kind == PERCENT:
        return serializers.DecimalField(
            max_digits=PERCENT_MAX_DIGITS, decimal_places=PERCENT_DECIMAL_PLACES
        )
    return serializers.IntegerField()


def _input_field(name: str, kind: str) -> serializers.Field:
    low, high = LIMITS[kind]
    if kind == PERCENT:
        positive = name in POSITIVE_FIELDS
        return serializers.DecimalField(
            max_digits=PERCENT_MAX_DIGITS,
            decimal_places=PERCENT_DECIMAL_PLACES,
            # Con un decimal, lo más chico que pasa de cero es 0,1.
            min_value=Decimal("0.1") if positive else low,
            max_value=high,
            error_messages={
                "min_value": (
                    "Debe ser mayor que cero." if positive else PERCENT_RANGE_FOR_VALIDATOR
                ),
                "max_value": PERCENT_RANGE_FOR_VALIDATOR,
                # 1000,0 no cabe en los dígitos antes de llegar a compararse con 100.
                "max_whole_digits": PERCENT_RANGE,
                "max_digits": PERCENT_RANGE,
                "max_decimal_places": "Usa máximo 1 decimal.",
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


# Los quince parámetros, en el orden de la lista única. Se arman desde ella para que agregar uno
# no obligue a tocar la API.
DryingValuesSerializer = type(
    "DryingValuesSerializer",
    (serializers.Serializer,),
    {name: _value_field(kind) for name, kind in FIELDS.items()},
)

DryingValuesInputSerializer = type(
    "DryingValuesInputSerializer",
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
    values = DryingValuesSerializer()
    # Viaja siempre, para que el cliente no tenga su propia copia de la línea base.
    baseline = DryingValuesSerializer()
    # 0 mientras el productor use la línea base.
    version = serializers.IntegerField()
    updated_at = serializers.DateTimeField(allow_null=True)
    updated_by = ParametersAuthorSerializer(allow_null=True)


class PostharvestParametersSaveSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Solo la cuenta técnica, y para ella obligatorio; en otra cuenta se ignora.
    producer = serializers.UUIDField(required=False)
    # 0 si el productor todavía usa la línea base.
    expected_version = serializers.IntegerField(min_value=0)
    values = DryingValuesInputSerializer()


class ProducerQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)
