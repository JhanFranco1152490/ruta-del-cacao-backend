from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin, RequireSomeFieldMixin

from ..choices import ControlMethod, PestDiseaseKind, SamplingUnit
from ..models import PestDisease


class PestDiseaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = PestDisease
        fields = [
            "id",
            "name",
            "kind",
            "scientific_name",
            "description",
            "is_active",
            "suggested_sampling_unit",
            "suggested_control_method",
        ]
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


def suggested_unit_field():
    return serializers.ChoiceField(choices=SamplingUnit.choices, required=False, allow_null=True)


def suggested_method_field():
    return serializers.ChoiceField(choices=ControlMethod.choices, required=False, allow_null=True)


class PestDiseaseCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = name_field()
    kind = serializers.ChoiceField(choices=PestDiseaseKind.choices)
    scientific_name = scientific_name_field()
    description = description_field()
    suggested_sampling_unit = suggested_unit_field()
    suggested_control_method = suggested_method_field()


class PestDiseaseUpdateSerializer(
    RequireSomeFieldMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    name = name_field(required=False)
    kind = serializers.ChoiceField(choices=PestDiseaseKind.choices, required=False)
    scientific_name = scientific_name_field()
    description = description_field(required=False)
    suggested_sampling_unit = suggested_unit_field()
    suggested_control_method = suggested_method_field()
    is_active = serializers.BooleanField(required=False)
