from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from .models import PostharvestFacility
from .status import FacilityStatus, facility_status


class FacilityFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class PostharvestFacilitySerializer(serializers.ModelSerializer):
    # La finca es de solo lectura: un elemento no cambia de finca.
    farm = FacilityFarmSerializer(read_only=True)
    producer_id = serializers.UUIDField(source="farm.producer_id", read_only=True)
    status = serializers.SerializerMethodField()
    # Si algún registro lo usa: lo deja el servicio, que lo calcula en la misma consulta.
    has_records = serializers.BooleanField(read_only=True)

    class Meta:
        model = PostharvestFacility
        fields = [
            "id",
            "farm",
            "producer_id",
            "facility_type",
            "name",
            "capacity_kg",
            "is_active",
            "status",
            "has_records",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=FacilityStatus.choices))
    def get_status(self, facility) -> str:
        return facility_status(facility)


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class PostharvestFacilityListSerializer(serializers.Serializer):
    results = PostharvestFacilitySerializer(many=True)


class PostharvestFacilityListQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)
