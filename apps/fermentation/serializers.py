from django.utils import timezone
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.common.contracts.harvest_representation import (
    HarvestRecorderSerializer,
    HarvestRepresentationSerializer,
)
from apps.common.serializers import full_name

from .alerts import next_turn_due_at
from .models import NOTES_MAX_LENGTH, FermentationProcess
from .rules import hours_between, numbered

# Las opciones del estado del lote se toman de su campo por la relación, sin importar su app: así
# el esquema las reconoce como el mismo enum de los lotes.
LOT_STATUS_CHOICES = (
    FermentationProcess._meta.get_field("lot").related_model._meta.get_field("status").choices
)


class FermentationLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LOT_STATUS_CHOICES)
    green_weight_kg = serializers.DecimalField(
        source="harvest.green_weight_kg", max_digits=7, decimal_places=1
    )
    # El origen que muestra la ficha del lote, para que la copia sin conexión la arme sola.
    harvest = HarvestRepresentationSerializer()


class FermentationFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class FermentationBoxSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    capacity_kg = serializers.DecimalField(max_digits=6, decimal_places=1)


class FermentationPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()


class FermentationTurnSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.IntegerField()
    turned_at = serializers.DateTimeField()
    hours_since_start = serializers.DecimalField(max_digits=6, decimal_places=1)
    temperature_c = serializers.DecimalField(max_digits=3, decimal_places=1)
    ph = serializers.DecimalField(max_digits=4, decimal_places=2)
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH)
    recorded_by = HarvestRecorderSerializer()
    version = serializers.IntegerField()


class FermentationResultSerializer(serializers.Serializer):
    ended_at = serializers.DateTimeField()
    duration_hours = serializers.DecimalField(max_digits=6, decimal_places=1)
    turn_count = serializers.IntegerField()
    notes = serializers.CharField()


class FermentationProcessSerializer(serializers.Serializer):
    lot = FermentationLotSerializer()
    farm = FermentationFarmSerializer(source="lot.harvest.plot.farm")
    facility = FermentationBoxSerializer()
    started_at = serializers.DateTimeField()
    over_capacity = serializers.BooleanField()
    responsible = serializers.SerializerMethodField()
    elapsed_hours = serializers.SerializerMethodField()
    next_turn_due_at = serializers.SerializerMethodField()
    turns = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def _now(self):
        # Un solo "ahora" por respuesta: todas las fermentaciones de una lista se cuentan igual.
        if "now" not in self.context:
            self.context["now"] = timezone.now()
        return self.context["now"]

    def get_responsible(self, process) -> FermentationPersonSerializer:
        account = process.responsible
        return FermentationPersonSerializer(
            {"id": account.pk, "full_name": full_name(account), "is_active": account.is_active}
        ).data

    @extend_schema_field(serializers.DecimalField(max_digits=6, decimal_places=1))
    def get_elapsed_hours(self, process):
        end = process.ended_at or self._now()
        return f"{hours_between(process.started_at, end):.1f}"

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_next_turn_due_at(self, process):
        if process.ended_at is not None:
            return None
        turns = list(process.turns.all())
        last = max((turn.turned_at for turn in turns), default=None)
        due = next_turn_due_at(process.started_at, last)
        return serializers.DateTimeField().to_representation(due)

    @extend_schema_field(FermentationTurnSerializer(many=True))
    def get_turns(self, process):
        rows = [
            {
                "id": turn.pk,
                "number": number,
                "turned_at": turn.turned_at,
                "hours_since_start": hours_between(process.started_at, turn.turned_at),
                "temperature_c": turn.temperature_c,
                "ph": turn.ph,
                "notes": turn.notes,
                "recorded_by": {
                    "id": turn.recorded_by.pk,
                    "full_name": full_name(turn.recorded_by),
                },
                "version": turn.version,
            }
            for number, turn in numbered(process.turns.all())
        ]
        return FermentationTurnSerializer(rows, many=True).data

    @extend_schema_field(FermentationResultSerializer(allow_null=True))
    def get_result(self, process):
        if process.ended_at is None:
            return None
        return FermentationResultSerializer(
            {
                "ended_at": process.ended_at,
                "duration_hours": hours_between(process.started_at, process.ended_at),
                "turn_count": len(process.turns.all()),
                "notes": process.end_notes,
            }
        ).data


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class FermentationListSerializer(serializers.Serializer):
    results = FermentationProcessSerializer(many=True)


class FermentationListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField(required=False)
    producer = serializers.UUIDField(required=False)


class StartOptionsQuerySerializer(serializers.Serializer):
    lot = serializers.UUIDField()


class StartOptionPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()
    assignable = serializers.BooleanField()


class StartOptionsSerializer(serializers.Serializer):
    facilities = FermentationBoxSerializer(many=True)
    responsibles = StartOptionPersonSerializer(many=True)
    green_weight_kg = serializers.DecimalField(max_digits=7, decimal_places=1)
    earliest_start_at = serializers.DateTimeField()


class LotFermentationSerializer(serializers.Serializer):
    # Lo que la fermentación agrega a la representación de un lote.
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    facility = serializers.CharField(source="facility.name")
