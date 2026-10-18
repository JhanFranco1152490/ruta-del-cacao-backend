from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import (
    ApiErrorSerializer,
    RejectUnknownFieldsMixin,
    RequireVersionedChangeMixin,
)

from .models import MAX_CAPACITY_KG, MIN_CAPACITY_KG, NAME_MAX_LENGTH, PostharvestFacility
from .status import FacilityStatus, facility_status

# Las opciones del estado del lote se toman de su campo por la relación, sin importar su app: así
# el esquema las reconoce como el mismo enum de los lotes.
LOT_STATUS_CHOICES = (
    PostharvestFacility._meta.get_field("current_lot")
    .related_model._meta.get_field("status")
    .choices
)


class FacilityFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class OccupyingLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LOT_STATUS_CHOICES)


class OccupiedBySerializer(serializers.Serializer):
    lot = OccupyingLotSerializer(source="current_lot")
    since = serializers.DateTimeField(source="occupied_since")


class PostharvestFacilitySerializer(serializers.ModelSerializer):
    # La finca es de solo lectura: un elemento no cambia de finca.
    farm = FacilityFarmSerializer(read_only=True)
    producer_id = serializers.UUIDField(source="farm.producer_id", read_only=True)
    status = serializers.SerializerMethodField()
    # El lote que está adentro y desde cuándo, o `null`. Lo cambian solo fermentación y secado.
    occupied_by = serializers.SerializerMethodField()
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
            "occupied_by",
            "has_records",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=FacilityStatus.choices))
    def get_status(self, facility) -> str:
        return facility_status(facility)

    @extend_schema_field(OccupiedBySerializer(allow_null=True))
    def get_occupied_by(self, facility) -> dict | None:
        if facility.current_lot_id is None:
            return None
        return OccupiedBySerializer(facility).data


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class PostharvestFacilityListSerializer(serializers.Serializer):
    results = PostharvestFacilitySerializer(many=True)


class PostharvestFacilityListQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class PostharvestFacilityCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    farm_id = serializers.UUIDField()
    facility_type = serializers.ChoiceField(choices=PostharvestFacility.FacilityType.choices)
    # Un nombre que solo tiene guiones lo rechaza el modelo (`clean`), que lo normaliza.
    name = serializers.CharField(max_length=NAME_MAX_LENGTH)
    capacity_kg = serializers.IntegerField(min_value=MIN_CAPACITY_KG, max_value=MAX_CAPACITY_KG)


class PostharvestFacilityUpdateSerializer(
    RequireVersionedChangeMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    # Sin `farm_id`: un elemento está construido en una finca y no se muda. Si llega, el mixin lo
    # rechaza como campo no permitido.
    facility_type = serializers.ChoiceField(
        choices=PostharvestFacility.FacilityType.choices, required=False
    )
    name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False)
    capacity_kg = serializers.IntegerField(
        min_value=MIN_CAPACITY_KG, max_value=MAX_CAPACITY_KG, required=False
    )
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class PostharvestFacilityDeleteSerializer(serializers.Serializer):
    # Query param del DELETE, con la versión leída: no se elimina un elemento que otra persona
    # acaba de cambiar.
    expected_version = serializers.IntegerField(min_value=1)


class ExistingFacilitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    facility_type = serializers.ChoiceField(choices=PostharvestFacility.FacilityType.choices)
    is_active = serializers.BooleanField()


class PostharvestFacilityConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y `existing` con `duplicate_facility_name`.
    current = PostharvestFacilitySerializer(required=False)
    existing = ExistingFacilitySerializer(required=False)
