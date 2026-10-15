from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin, RequireSomeFieldMixin

from .choices import ControlMethod, ControlMode, PestDiseaseKind, SamplingMethod, SamplingUnit
from .models import Detection, PestDisease, PhytosanitaryMonitoring


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


# --- Resultado del monitoreo y controles --------------------------------------------------------
# Los serializers solo revisan tipos, largos y qué campos lleva cada modo; las reglas (unidades
# mayores que cero, afectadas hasta las evaluadas, sin repetir, qué se hizo) las aplica el
# servicio, con el mensaje de cada regla.


class ControlInputSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    input_id = serializers.UUIDField()
    # En la unidad del insumo. Que sea mayor que cero lo valida el servicio, con su mensaje.
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)


SCHEDULED_ONLY = ("scheduled_date", "planned_input_id")
DONE_ONLY = ("inputs", "done_date", "captured_at")


class ControlSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # El control que se crea dentro de la planilla del monitoreo. Uno hecho en el momento toma la
    # fecha del monitoreo y queda a nombre de quien lo registra, así que no lleva fecha ni
    # responsable.
    id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=ControlMode.choices)
    method = serializers.ChoiceField(
        choices=ControlMethod.choices, required=False, allow_null=True, default=None
    )
    method_description = serializers.CharField(
        max_length=80, required=False, allow_null=True, allow_blank=True, default=None
    )
    scheduled_date = serializers.DateField(required=False)
    assignee_id = serializers.UUIDField(required=False)
    # Una referencia para quien lo aplique: no descuenta nada.
    planned_input_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    inputs = ControlInputSerializer(many=True, required=False)

    # Lo que pide y lo que no admite un control realizado en este formulario.
    done_required: tuple = ()
    done_foreign: tuple = (*SCHEDULED_ONLY, "assignee_id")

    def validate(self, attrs):
        scheduled = attrs["mode"] == ControlMode.SCHEDULED
        required = ("scheduled_date", "assignee_id") if scheduled else self.done_required
        foreign = DONE_ONLY if scheduled else self.done_foreign
        errors = {name: ["Este campo es obligatorio."] for name in required if name not in attrs}
        errors.update(
            {
                name: ["No corresponde a este modo."]
                for name in foreign
                if attrs.get(name) not in (None, [])
            }
        )
        if errors:
            raise serializers.ValidationError(errors)
        attrs.setdefault("inputs", [])
        return attrs


class DetectionControlSerializer(ControlSerializer):
    # El control que se crea desde una detección, cuando se decide después del recorrido: uno
    # realizado dice su fecha y su responsable.
    done_date = serializers.DateField(required=False)
    # Hora del dispositivo al capturar; informativa.
    captured_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    done_required = ("done_date", "assignee_id")
    done_foreign = SCHEDULED_ONLY


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
    # Ninguno por ahora, hecho en el momento o programado para después.
    control = ControlSerializer(required=False, allow_null=True, default=None)


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


class DetectionOutputSerializer(serializers.ModelSerializer):
    pest_disease = PestDiseaseRefSerializer(allow_null=True)
    controls = serializers.SerializerMethodField()

    class Meta:
        model = Detection
        fields = [
            "id",
            "pest_disease",
            "other_description",
            "affected_units",
            "incidence",
            "controls",
        ]
        read_only_fields = fields

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
        # La más alta primero: lo que más urge atender.
        rows = sorted(monitoring.detections.all(), key=lambda row: (-row.incidence, str(row.pk)))
        return DetectionOutputSerializer(rows, many=True).data

    def get_detections_without_control(self, monitoring) -> int:
        return sum(1 for row in monitoring.detections.all() if not row.treatments.all())

    def get_evidence_count(self, monitoring) -> int:
        return 0


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
        return 0
