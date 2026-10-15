from rest_framework import serializers

from ..choices import ControlMethod, SamplingUnit
from ..models import Detection, PestDisease, PhytosanitaryMonitoring
from .people import PersonSerializer

# --- En la representación de la actividad -------------------------------------------------------
# Se leen de lo que la consulta de actividades ya precargó (ver `apps.py`): nada de aquí hace
# otra consulta por fila.


class PestDiseaseRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = PestDisease
        fields = ["id", "name", "kind", "is_active"]
        read_only_fields = fields


class DetectionControlRowSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="pk")
    method = serializers.ChoiceField(choices=ControlMethod.choices, allow_null=True)
    method_description = serializers.CharField(allow_null=True)
    scheduled_date = serializers.DateField(source="activity.scheduled_date")
    # Programado, retrasado, vencido o realizado, calculado con la fecha de hoy.
    state = serializers.CharField(source="activity.state_today")
    done_date = serializers.DateField(source="activity.done_date", allow_null=True)


class ControlRequestInfoSerializer(serializers.Serializer):
    # Quien registró el monitoreo pidió que le programen un control. `dismissed_*` dice quién
    # decidió después que no requiere control.
    requested_by = PersonSerializer(source="control_requested_by", allow_null=True)
    requested_at = serializers.DateTimeField(source="control_requested_at")
    dismissed_by = PersonSerializer(source="control_dismissed_by", allow_null=True)
    dismissed_at = serializers.DateTimeField(source="control_dismissed_at", allow_null=True)


class DetectionOutputSerializer(serializers.ModelSerializer):
    pest_disease = PestDiseaseRefSerializer(allow_null=True)
    controls = serializers.SerializerMethodField()
    # `null` si nadie pidió que le programen un control.
    control_request = serializers.SerializerMethodField()

    class Meta:
        model = Detection
        fields = [
            "id",
            "pest_disease",
            "other_description",
            "affected_units",
            "incidence",
            "controls",
            "control_request",
        ]
        read_only_fields = fields

    def get_control_request(self, detection) -> ControlRequestInfoSerializer(allow_null=True):
        if detection.control_requested_at is None:
            return None
        return ControlRequestInfoSerializer(detection).data

    def get_controls(self, detection) -> DetectionControlRowSerializer(many=True):
        # En orden de fecha, como se aplicaron o se van a aplicar.
        rows = sorted(
            detection.treatments.all(),
            key=lambda treatment: (treatment.activity.scheduled_date, str(treatment.pk)),
        )
        return DetectionControlRowSerializer(rows, many=True).data


class ActivityMonitoringSerializer(serializers.ModelSerializer):
    detections = serializers.SerializerMethodField()
    # Las detecciones que no tienen ningún control: el calendario avisa sin cargar el detalle.
    detections_without_control = serializers.SerializerMethodField()
    evidence_count = serializers.SerializerMethodField()

    class Meta:
        model = PhytosanitaryMonitoring
        fields = [
            "sampling_unit",
            "evaluated_units",
            "sampling_method",
            "notes",
            "no_presence",
            "detections",
            "detections_without_control",
            "evidence_count",
        ]
        read_only_fields = fields

    def get_detections(self, monitoring) -> DetectionOutputSerializer(many=True):
        # La más alta primero: lo que más urge atender. El historial filtrado por plaga pasa en el
        # contexto cuáles mostrar.
        keep = self.context.get("keep_detection", lambda detection: True)
        rows = sorted(
            (row for row in monitoring.detections.all() if keep(row)),
            key=lambda row: (-row.incidence, str(row.pk)),
        )
        return DetectionOutputSerializer(rows, many=True).data

    def get_detections_without_control(self, monitoring) -> int:
        return sum(1 for row in monitoring.detections.all() if not row.treatments.all())

    def get_evidence_count(self, monitoring) -> int:
        # Las fotos no van en la lista: el contador dice si hay algo que ver en el detalle.
        return len(monitoring.evidence.all())


class PlannedInputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class ControlOfSerializer(serializers.Serializer):
    detection_id = serializers.UUIDField()
    monitoring_id = serializers.UUIDField(source="detection.monitoring_id")
    pest_disease = PestDiseaseRefSerializer(source="detection.pest_disease", allow_null=True)
    other_description = serializers.CharField(
        source="detection.other_description", allow_null=True
    )
    incidence = serializers.DecimalField(
        source="detection.incidence", max_digits=5, decimal_places=2
    )
    # Para decir "24 % de árboles" o "24 % de mazorcas".
    sampling_unit = serializers.ChoiceField(
        source="detection.monitoring.sampling_unit", choices=SamplingUnit.choices
    )
    monitoring_done_date = serializers.DateField(source="detection.monitoring.activity.done_date")
    method = serializers.ChoiceField(choices=ControlMethod.choices, allow_null=True)
    method_description = serializers.CharField(allow_null=True)
    # Una referencia para quien lo aplique: no descuenta nada.
    planned_input = PlannedInputSerializer(allow_null=True)
    evidence_count = serializers.SerializerMethodField()

    def get_evidence_count(self, treatment) -> int:
        return len(treatment.evidence.all())
