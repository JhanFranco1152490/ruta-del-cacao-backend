from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import (
    ApiErrorSerializer,
    RejectUnknownFieldsMixin,
    RequireVersionedChangeMixin,
)

from .models import NAME_MAX_LENGTH, AgriculturalInput


class InputProducerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class AgriculturalInputSerializer(serializers.ModelSerializer):
    # De quién es el insumo: solo lectura, un insumo no cambia de dueño.
    producer = InputProducerSerializer(read_only=True)
    # Si algún registro lo usa: lo deja el servicio, que lo calcula en la misma consulta.
    has_records = serializers.BooleanField(read_only=True)

    class Meta:
        model = AgriculturalInput
        fields = [
            "id",
            "producer",
            "name",
            "input_type",
            "unit",
            "package_type",
            "package_size",
            "is_active",
            "has_records",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class AgriculturalInputListSerializer(serializers.Serializer):
    results = AgriculturalInputSerializer(many=True)


class AgriculturalInputWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # El mínimo lo revisa el modelo (`clean`), que ve el nombre ya recortado.
    name = serializers.CharField(max_length=NAME_MAX_LENGTH)
    input_type = serializers.ChoiceField(choices=AgriculturalInput.InputType.choices)
    unit = serializers.ChoiceField(choices=AgriculturalInput.Unit.choices)
    package_type = serializers.ChoiceField(
        choices=AgriculturalInput.PackageType.choices, required=False, allow_null=True
    )
    package_size = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )

    def to_model_data(self) -> dict:
        return dict(self.validated_data)


class AgriculturalInputCreateSerializer(AgriculturalInputWriteSerializer):
    # Solo lo manda la cuenta técnica, que no tiene un productor propio. Para cualquier otra
    # cuenta es el de la sesión y mandarlo es un error (ver `create_input`).
    producer_id = serializers.UUIDField(required=False)


class AgriculturalInputUpdateSerializer(
    RequireVersionedChangeMixin, AgriculturalInputWriteSerializer
):
    name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False)
    input_type = serializers.ChoiceField(
        choices=AgriculturalInput.InputType.choices, required=False
    )
    unit = serializers.ChoiceField(choices=AgriculturalInput.Unit.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class AgriculturalInputDeleteSerializer(serializers.Serializer):
    # Query param del DELETE, con la versión leída: no se elimina un insumo que otra persona
    # acaba de cambiar.
    expected_version = serializers.IntegerField(min_value=1)


class AgriculturalInputListQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class ExistingInputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    input_type = serializers.ChoiceField(choices=AgriculturalInput.InputType.choices)
    is_active = serializers.BooleanField()


class AgriculturalInputConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y `existing` con `duplicate_input`.
    current = AgriculturalInputSerializer(required=False)
    existing = ExistingInputSerializer(required=False)
