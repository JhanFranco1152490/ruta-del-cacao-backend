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
    # Los insumos usados llegan cuando exista el catálogo de insumos; mientras tanto, ninguno.
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

    def get_inputs(self, activity) -> list[dict]:
        return []

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


class CompletionSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    done_date = serializers.DateField()
    # Los insumos se aceptan cuando exista el catálogo de insumos; hoy debe venir vacío.
    inputs = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    # Hora del dispositivo al capturar; informativa, así que no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class AssigneeQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class AssigneeListSerializer(serializers.Serializer):
    results = AssigneeSerializer(many=True)


class ActivityConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta. `current` llega con `stale_version`, para cargar los valores vigentes
    # sin otra consulta.
    current = AgriculturalActivitySerializer(required=False)
