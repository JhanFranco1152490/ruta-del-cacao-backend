from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from ..choices import ControlMethod, ControlMode, SamplingMethod, SamplingUnit

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
