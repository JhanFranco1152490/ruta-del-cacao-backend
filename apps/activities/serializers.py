from rest_framework import serializers

from apps.common.serializers import (
    ApiErrorSerializer,
    RejectUnknownFieldsMixin,
    RequireVersionedChangeMixin,
)

from .choices import ActivityStatus, ActivityType
from .models import AgriculturalActivity
from .state import ActivityState, activity_state, today_in_bogota


def full_name(account) -> str:
    return account.get_full_name() or account.email


class ActivityFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class ActivityPlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    is_active = serializers.BooleanField()
    farm = ActivityFarmSerializer()


class AssigneeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()


class UsedInputItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    unit = serializers.CharField()
    package_type = serializers.CharField(allow_null=True)
    package_size = serializers.DecimalField(max_digits=10, decimal_places=3, allow_null=True)
    is_active = serializers.BooleanField()


class UsedInputOutputSerializer(serializers.Serializer):
    input = UsedInputItemSerializer()
    # En la unidad del insumo, que no cambia una vez usado.
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)


class RecorderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


class AgriculturalActivitySerializer(serializers.ModelSerializer):
    plot = ActivityPlotSerializer()
    producer_id = serializers.UUIDField(source="plot.farm.producer_id")
    status = serializers.ChoiceField(choices=ActivityStatus.choices)
    state = serializers.SerializerMethodField()
    days_late = serializers.SerializerMethodField()
    assignee = serializers.SerializerMethodField()
    # Vacío mientras no esté realizada. Un insumo desactivado después sigue saliendo, marcado.
    inputs = serializers.SerializerMethodField()
    completed_by = serializers.SerializerMethodField()

    class Meta:
        model = AgriculturalActivity
        fields = [
            "id",
            "plot",
            "producer_id",
            "activity_type",
            "other_description",
            "scheduled_date",
            "status",
            "state",
            "days_late",
            "assignee",
            "done_date",
            "inputs",
            "completed_by",
            "completed_at",
            "version",
            "created_at",
            "updated_at",
        ]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields

    def _state(self, activity):
        # Una sola fecha de hoy por respuesta: si la petición cruza la medianoche, todas las
        # actividades se calculan con el mismo día.
        if "today" not in self.context:
            self.context["today"] = today_in_bogota()
        return activity_state(activity, self.context["today"])

    def get_state(self, activity) -> ActivityState:
        return self._state(activity)[0]

    def get_days_late(self, activity) -> int:
        return self._state(activity)[1]

    def get_assignee(self, activity) -> AssigneeSerializer:
        account = activity.assignee
        return {"id": account.pk, "full_name": full_name(account), "is_active": account.is_active}

    def get_inputs(self, activity) -> UsedInputOutputSerializer(many=True):
        rows = sorted(activity.inputs.all(), key=lambda row: (row.input.name, str(row.input_id)))
        return UsedInputOutputSerializer(rows, many=True).data

    def get_completed_by(self, activity) -> RecorderSerializer(allow_null=True):
        account = activity.completed_by
        return None if account is None else {"id": account.pk, "full_name": full_name(account)}


class ActivityCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el dispositivo, para que un reenvío no duplique; si no llega, lo genera el
    # servidor.
    id = serializers.UUIDField(required=False)
    plot_id = serializers.UUIDField()
    activity_type = serializers.ChoiceField(choices=ActivityType.choices)
    # El largo lo valida el servicio, con el mensaje de la regla.
    other_description = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, trim_whitespace=False
    )
    scheduled_date = serializers.DateField()
    assignee_id = serializers.UUIDField()


class ActivityUpdateSerializer(
    RequireVersionedChangeMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    # La parcela no está: una actividad no cambia de parcela.
    activity_type = serializers.ChoiceField(choices=ActivityType.choices, required=False)
    other_description = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, trim_whitespace=False
    )
    scheduled_date = serializers.DateField(required=False)
    assignee_id = serializers.UUIDField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class ActivityDeleteQuerySerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class UsedInputSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    input_id = serializers.UUIDField()
    # En la unidad del insumo. Que sea mayor que cero lo valida el servicio, con su mensaje.
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)


class CompletionSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    done_date = serializers.DateField()
    # Ninguno, uno o varios: una labor sin insumos se registra con la lista vacía.
    inputs = UsedInputSerializer(many=True, required=False, default=list)
    # Hora del dispositivo al capturar; informativa, así que no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


MAX_PERIOD_DAYS = 120


class ActivityListQuerySerializer(serializers.Serializer):
    # Cubre el mes que se ve (hasta 42 días de cuadrícula) y la copia sin conexión (del mes
    # anterior a dos meses después), sin abrir la puerta a pedir años enteros sin paginar.

    def get_fields(self):
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo.
        return {
            "from": serializers.DateField(),
            "to": serializers.DateField(),
            "producer": serializers.UUIDField(required=False),
        }

    def validate(self, attrs):
        if attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["Debe ser igual o posterior a `from`."]})
        if (attrs["to"] - attrs["from"]).days + 1 > MAX_PERIOD_DAYS:
            raise serializers.ValidationError(
                {"to": [f"El periodo no puede pasar de {MAX_PERIOD_DAYS} días."]}
            )
        return attrs


class ActivityListSerializer(serializers.Serializer):
    results = AgriculturalActivitySerializer(many=True)


class AssigneeQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class AssigneeListSerializer(serializers.Serializer):
    results = AssigneeSerializer(many=True)


class ActivityConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta. `current` llega con `stale_version`, para cargar los valores vigentes
    # sin otra consulta.
    current = AgriculturalActivitySerializer(required=False)
