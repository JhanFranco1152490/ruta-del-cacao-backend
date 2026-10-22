from rest_framework import serializers

from apps.common.serializers import full_name

from .fields import FIELDS, PERCENT, PERCENT_DECIMAL_PLACES, PERCENT_MAX_DIGITS


def _value_field(kind: str) -> serializers.Field:
    if kind == PERCENT:
        return serializers.DecimalField(
            max_digits=PERCENT_MAX_DIGITS, decimal_places=PERCENT_DECIMAL_PLACES
        )
    return serializers.IntegerField()


# Los quince parámetros, en el orden de la lista única. Se arma desde ella para que agregar uno no
# obligue a tocar la API.
DryingValuesSerializer = type(
    "DryingValuesSerializer",
    (serializers.Serializer,),
    {name: _value_field(kind) for name, kind in FIELDS.items()},
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


class ProducerQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)
