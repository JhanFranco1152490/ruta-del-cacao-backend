from dataclasses import asdict

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.common.contracts.harvest_representation import (
    HarvestRecorderSerializer,
    HarvestRepresentationSerializer,
)
from apps.common.contracts.postharvest_parameters import fermentation_parameters
from apps.common.hours import hours_between
from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin, full_name

from .alerts import next_turn_due_at
from .models import MAX_PH, MAX_TEMPERATURE_C, NOTES_MAX_LENGTH, FermentationProcess
from .rules import numbered

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


# Lo que el productor configuró para fermentar: cuándo toca cada volteo y la temperatura y el pH de
# referencia. Viajan con cada fermentación para que el teléfono calcule el próximo volteo sin
# conexión y muestre la referencia al registrar uno.
class FermentationParametersSerializer(serializers.Serializer):
    first_turn_hours = serializers.IntegerField()
    next_turn_hours = serializers.IntegerField()
    temperature_min_c = serializers.DecimalField(max_digits=4, decimal_places=1)
    temperature_max_c = serializers.DecimalField(max_digits=4, decimal_places=1)
    ph_min = serializers.DecimalField(max_digits=4, decimal_places=2)
    ph_max = serializers.DecimalField(max_digits=4, decimal_places=2)


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


def turn_row(turn, number: int, started_at) -> dict:
    """Un volteo como lo entrega la API, con su número y las horas desde el inicio."""
    return {
        "id": turn.pk,
        "number": number,
        "turned_at": turn.turned_at,
        "hours_since_start": hours_between(started_at, turn.turned_at),
        "temperature_c": turn.temperature_c,
        "ph": turn.ph,
        "notes": turn.notes,
        "recorded_by": {"id": turn.recorded_by.pk, "full_name": full_name(turn.recorded_by)},
        "version": turn.version,
    }


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
    parameters = serializers.SerializerMethodField()
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

    def _parameters(self, process):
        # Una lectura por productor, aunque la lista tenga muchas fermentaciones suyas.
        cache = self.context.setdefault("fermentation_parameters", {})
        producer_id = process.lot.harvest.plot.farm.producer_id
        if producer_id not in cache:
            cache[producer_id] = fermentation_parameters(producer_id)
        return cache[producer_id]

    @extend_schema_field(FermentationParametersSerializer)
    def get_parameters(self, process):
        return FermentationParametersSerializer(asdict(self._parameters(process))).data

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_next_turn_due_at(self, process):
        if process.ended_at is not None:
            return None
        turns = list(process.turns.all())
        last = max((turn.turned_at for turn in turns), default=None)
        due = next_turn_due_at(process.started_at, last, self._parameters(process))
        return serializers.DateTimeField().to_representation(due)

    @extend_schema_field(FermentationTurnSerializer(many=True))
    def get_turns(self, process):
        rows = [
            turn_row(turn, number, process.started_at)
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


class FermentationStartSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    lot_id = serializers.UUIDField()
    facility_id = serializers.UUIDField()
    started_at = serializers.DateTimeField()
    responsible_id = serializers.UUIDField()
    # Que quien registra vio el aviso de que el lote supera la capacidad del cajón.
    confirm_over_capacity = serializers.BooleanField(default=False)


class FermentationStartUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    facility_id = serializers.UUIDField(required=False)
    started_at = serializers.DateTimeField(required=False)
    responsible_id = serializers.UUIDField(required=False)
    confirm_over_capacity = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        # La confirmación sola no cambia nada.
        if not {"facility_id", "started_at", "responsible_id"} & set(attrs):
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class FermentationConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version`, y `current_status` con `lot_invalid_status`.
    current = FermentationProcessSerializer(required=False)
    current_status = serializers.CharField(required=False)


class CapacityErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: llega con `lot_exceeds_capacity`.
    capacity_kg = serializers.DecimalField(max_digits=6, decimal_places=1, required=False)
    green_weight_kg = serializers.DecimalField(max_digits=7, decimal_places=1, required=False)


TEMPERATURE_MESSAGE = "La temperatura debe ser mayor que 0 °C y hasta 80 °C."
# El texto que muestra el formulario del volteo.
PH_MESSAGE = "pH válido entre 0 y 14"


class TurnContentMixin(serializers.Serializer):
    # Un dígito más de los que guarda la base: así 80,1 °C o pH 15 llegan a la regla y responden su
    # rango, en vez de un error de cantidad de dígitos.
    temperature_c = serializers.DecimalField(max_digits=4, decimal_places=1)
    ph = serializers.DecimalField(max_digits=5, decimal_places=2)
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH, allow_blank=True, required=False)
    turned_at = serializers.DateTimeField()

    def validate_temperature_c(self, value):
        if not 0 < value <= MAX_TEMPERATURE_C:
            raise serializers.ValidationError(TEMPERATURE_MESSAGE)
        return value

    def validate_ph(self, value):
        if not 0 <= value <= MAX_PH:
            raise serializers.ValidationError(PH_MESSAGE)
        return value


class FermentationTurnCreateSerializer(RejectUnknownFieldsMixin, TurnContentMixin):
    # Lo genera el dispositivo, para que un reenvío desde la cola no cree otro volteo.
    id = serializers.UUIDField()
    # La hora del dispositivo al guardar, informativa.
    captured_at = serializers.DateTimeField(required=False, allow_null=True)


class FermentationTurnUpdateSerializer(RejectUnknownFieldsMixin, TurnContentMixin):
    expected_version = serializers.IntegerField(min_value=1, required=False)

    def get_fields(self):
        fields = super().get_fields()
        for name in ("turned_at", "temperature_c", "ph", "notes"):
            fields[name].required = False
        return fields

    def validate(self, attrs):
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class FermentationTurnDeleteSerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class DuplicateTurnSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.IntegerField()


class TurnConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `existing` llega con
    # `duplicate_turn_time` y `current` con `stale_version`.
    existing = DuplicateTurnSerializer(required=False)
    current = FermentationTurnSerializer(required=False)


class FermentationFinishSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    ended_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH, allow_blank=True, required=False)
