from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from .models import CacaoVariety


class CacaoVarietySerializer(serializers.ModelSerializer):
    class Meta:
        model = CacaoVariety
        fields = ["id", "name", "description", "is_active"]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class CacaoVarietyListSerializer(serializers.Serializer):
    results = CacaoVarietySerializer(many=True)


class CacaoVarietyListQuerySerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)


class CacaoVarietyCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=60)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CacaoVarietyUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=60, required=False)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs
