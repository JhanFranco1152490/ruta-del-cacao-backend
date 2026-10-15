from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin, RequireSomeFieldMixin

from .choices import PestDiseaseKind, SamplingMethod, SamplingUnit
from .models import PestDisease


class PestDiseaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = PestDisease
        fields = ["id", "name", "kind", "scientific_name", "description", "is_active"]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class PestDiseaseListSerializer(serializers.Serializer):
    results = PestDiseaseSerializer(many=True)


class PestDiseaseListQuerySerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)


def name_field(**kwargs):
    return serializers.CharField(min_length=2, max_length=60, **kwargs)


def scientific_name_field():
    return serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)


def description_field(**kwargs):
    return serializers.CharField(max_length=300, **kwargs)


class PestDiseaseCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = name_field()
    kind = serializers.ChoiceField(choices=PestDiseaseKind.choices)
    scientific_name = scientific_name_field()
    description = description_field()


class PestDiseaseUpdateSerializer(
    RequireSomeFieldMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    name = name_field(required=False)
    kind = serializers.ChoiceField(choices=PestDiseaseKind.choices, required=False)
    scientific_name = scientific_name_field()
    description = description_field(required=False)
    is_active = serializers.BooleanField(required=False)


# --- Resultado del monitoreo --------------------------------------------------------------------
# Los serializers solo revisan tipos y largos; las reglas (unidades mayores que cero, afectadas
# hasta las evaluadas, sin repetir) las aplica el servicio, con el mensaje de cada regla.


class DetectionWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el dispositivo: el control de una detección que sigue en la cola se programa con
    # este `id`.
    id = serializers.UUIDField()
    pest_disease_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    # Lo que escribió el capataz al elegir "Otra".
    other_description = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True, default=None
    )
    affected_units = serializers.IntegerField()


class MonitoringResultSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    done_date = serializers.DateField()
    sampling_unit = serializers.ChoiceField(choices=SamplingUnit.choices)
    evaluated_units = serializers.IntegerField()
    sampling_method = serializers.ChoiceField(
        choices=SamplingMethod.choices, required=False, allow_null=True, default=None
    )
    notes = serializers.CharField(
        max_length=500, required=False, allow_null=True, allow_blank=True, default=None
    )
    no_presence = serializers.BooleanField(required=False, default=False)
    detections = DetectionWriteSerializer(many=True, required=False, default=list)
    # Hora del dispositivo al capturar; informativa, así que no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
