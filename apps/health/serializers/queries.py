from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from ..choices import SamplingUnit
from ..models import Detection
from .representation import PestDiseaseRefSerializer

# --- Historial fitosanitario --------------------------------------------------------------------


class HistoryQuerySerializer(serializers.Serializer):
    def get_fields(self):
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo.
        return {
            "from": serializers.DateField(required=False),
            "to": serializers.DateField(required=False),
            "pest_disease": serializers.UUIDField(required=False),
            "other": serializers.BooleanField(required=False, default=False),
        }

    def validate(self, attrs):
        if attrs.get("from") and attrs.get("to") and attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["Debe ser igual o posterior a `from`."]})
        if attrs.get("pest_disease") and attrs["other"]:
            raise serializers.ValidationError(
                {"other": ["Filtra por una plaga o enfermedad o por Otra, no por las dos."]}
            )
        return attrs


class PestSummarySerializer(serializers.Serializer):
    pest_disease = PestDiseaseRefSerializer(allow_null=True)
    other_description = serializers.CharField(allow_null=True)
    sampling_unit = serializers.ChoiceField(choices=SamplingUnit.choices)
    latest_incidence = serializers.DecimalField(max_digits=5, decimal_places=2)
    # La del monitoreo anterior que contó lo mismo (árboles o mazorcas); `null` si no hay.
    previous_incidence = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    latest_date = serializers.DateField()


# --- Detecciones sin control --------------------------------------------------------------------


class WaitingMonitoringSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="pk")
    done_date = serializers.DateField(source="activity.done_date")


class WaitingFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class WaitingPlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    farm = WaitingFarmSerializer()


class WaitingDetectionSerializer(serializers.ModelSerializer):
    pest_disease = PestDiseaseRefSerializer(allow_null=True)
    sampling_unit = serializers.ChoiceField(
        source="monitoring.sampling_unit", choices=SamplingUnit.choices
    )
    monitoring = WaitingMonitoringSerializer()
    plot = WaitingPlotSerializer(source="monitoring.activity.plot")

    class Meta:
        model = Detection
        fields = [
            "id",
            "pest_disease",
            "other_description",
            "affected_units",
            "incidence",
            "sampling_unit",
            "monitoring",
            "plot",
        ]
        read_only_fields = fields


@extend_schema_serializer(many=False)
class WaitingDetectionListSerializer(serializers.Serializer):
    results = WaitingDetectionSerializer(many=True)


class WaitingQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)
