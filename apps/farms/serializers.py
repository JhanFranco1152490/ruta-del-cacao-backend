from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin
from apps.common.territorial import get_department, get_municipality

from .exceptions import LocationRequired
from .models import Farm

# Nombre del campo en la API -> nombre en el modelo. La API habla de `*_id` porque el cliente
# elige una opción del catálogo; el modelo guarda el código DIVIPOLA.
API_TO_MODEL_FIELDS = {"department_id": "department_code", "municipality_id": "municipality_code"}
MODEL_TO_API_FIELDS = {model: api for api, model in API_TO_MODEL_FIELDS.items()}


class TerritoryReferenceSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class LocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)


class FarmSerializer(serializers.ModelSerializer):
    department = serializers.SerializerMethodField()
    municipality = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()

    class Meta:
        model = Farm
        fields = [
            "id",
            "name",
            "department",
            "municipality",
            "details",
            "area_hectares",
            "altitude_masl",
            "location",
            "version",
            "is_active",
            "captured_at",
            "created_at",
            "updated_at",
        ]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields

    @extend_schema_field(TerritoryReferenceSerializer)
    def get_department(self, farm) -> dict:
        department = get_department(farm.department_code)
        return {"id": department.code, "name": department.name}

    @extend_schema_field(TerritoryReferenceSerializer)
    def get_municipality(self, farm) -> dict:
        municipality = get_municipality(farm.municipality_code)
        return {"id": municipality.code, "name": municipality.name}

    @extend_schema_field(LocationSerializer)
    def get_location(self, farm) -> dict:
        return LocationSerializer(farm).data


class FarmWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=200)
    department_id = serializers.CharField(max_length=2)
    municipality_id = serializers.CharField(max_length=5)
    details = serializers.CharField(required=False, allow_blank=True, default="")
    area_hectares = serializers.DecimalField(max_digits=10, decimal_places=2)
    altitude_masl = serializers.IntegerField()
    # No se marcan como requeridas para que su ausencia responda `location_required` (ver
    # validate) y no un error genérico de campo. Sin `max_digits`: un valor como 100 o -1000 es
    # una coordenada fuera de rango y debe responder `invalid_coordinates`, y eso lo decide el
    # modelo; si el serializer lo cortara antes, llegaría como un error genérico.
    latitude = serializers.DecimalField(max_digits=None, decimal_places=7, required=False)
    longitude = serializers.DecimalField(max_digits=None, decimal_places=7, required=False)

    def validate(self, attrs):
        if "latitude" not in attrs or "longitude" not in attrs:
            raise LocationRequired()
        return attrs

    def to_model_data(self) -> dict:
        return {
            API_TO_MODEL_FIELDS.get(name, name): value
            for name, value in self.validated_data.items()
        }


class FarmCreateSerializer(FarmWriteSerializer):
    # Lo genera el dispositivo cuando registra sin conexión; si no llega, lo genera el servidor.
    id = serializers.UUIDField(required=False)
    # Hora del dispositivo al capturar; informativa, así que no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(required=False, allow_null=True)


class FarmUpdateSerializer(FarmWriteSerializer):
    details = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)

    def validate(self, attrs):
        # Con partial=True ningún campo es obligatorio, ni siquiera la versión; y la ubicación
        # puede quedar como está, así que no se exige que llegue.
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class FarmConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y con `farm_id_conflict` de una finca propia, para mostrar la versión del
    # servidor sin otra consulta. Nunca con una finca de otro productor.
    current = FarmSerializer(required=False)


class FarmMunicipalityCountSerializer(serializers.Serializer):
    municipality_id = serializers.CharField(source="municipality_code")
    farm_count = serializers.IntegerField()


class FarmMapProducerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class FarmMapPointSerializer(serializers.ModelSerializer):
    location = serializers.SerializerMethodField()
    producer = FarmMapProducerSerializer()

    class Meta:
        model = Farm
        fields = ["id", "name", "is_active", "location", "producer"]
        read_only_fields = fields

    @extend_schema_field(LocationSerializer)
    def get_location(self, farm) -> dict:
        return LocationSerializer(farm).data
