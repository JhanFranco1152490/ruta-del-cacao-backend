from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from .models import Buyer


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
