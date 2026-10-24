from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.choices import DocumentType
from apps.common.serializers import (
    ApiErrorSerializer,
    RejectUnknownFieldsMixin,
    RequireVersionedChangeMixin,
)

from .models import NAME_MAX_LENGTH, Buyer

OPTIONAL_FIELDS = ("contact_name", "phone", "email")


class BuyerProducerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class BuyerSerializer(serializers.ModelSerializer):
    # De quién es el comprador: solo lectura, un comprador no cambia de productor.
    producer = BuyerProducerSerializer(read_only=True)
    # Si algún registro lo usa: lo deja el servicio, que lo calcula en la misma consulta.
    has_records = serializers.BooleanField(read_only=True)

    class Meta:
        model = Buyer
        fields = [
            "id",
            "producer",
            "name",
            "document_type",
            "identity_document",
            "buyer_type",
            "contact_name",
            "phone",
            "email",
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
class BuyerListSerializer(serializers.Serializer):
    results = BuyerSerializer(many=True)


class BuyerListQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class BuyerWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Los mínimos, el formato del documento y del teléfono y la regla de teléfono o correo los
    # revisa el modelo, que ve los valores ya recortados.
    name = serializers.CharField(max_length=NAME_MAX_LENGTH)
    document_type = serializers.ChoiceField(choices=DocumentType.choices)
    identity_document = serializers.CharField(max_length=15)
    buyer_type = serializers.ChoiceField(choices=Buyer.BuyerType.choices)
    contact_name = serializers.CharField(
        max_length=NAME_MAX_LENGTH, required=False, allow_blank=True, allow_null=True
    )
    phone = serializers.CharField(max_length=10, required=False, allow_blank=True, allow_null=True)
    email = serializers.CharField(
        max_length=254, required=False, allow_blank=True, allow_null=True
    )

    def to_model_data(self) -> dict:
        data = dict(self.validated_data)
        for name in OPTIONAL_FIELDS:
            if name in data and not data[name]:
                data[name] = None
        if data.get("email"):
            data["email"] = data["email"].lower()
        return data


class BuyerCreateSerializer(BuyerWriteSerializer):
    # Solo lo manda la cuenta técnica, que no tiene un productor propio. Para cualquier otra
    # cuenta es el de la sesión y mandarlo es un error (ver `create_buyer`).
    producer_id = serializers.UUIDField(required=False)


class BuyerUpdateSerializer(RequireVersionedChangeMixin, BuyerWriteSerializer):
    name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False)
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    identity_document = serializers.CharField(max_length=15, required=False)
    buyer_type = serializers.ChoiceField(choices=Buyer.BuyerType.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class ExistingBuyerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class BuyerConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y `existing` con `duplicate_document`.
    current = BuyerSerializer(required=False)
    existing = ExistingBuyerSerializer(required=False)
