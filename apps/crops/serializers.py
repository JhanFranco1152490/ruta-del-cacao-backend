from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin

from .choices import ManagementSystem, Propagation, ShadeType, Stage
from .fields import PlantingMonthField
from .models import (
    MAX_COMMON_NAMES,
    CacaoVariety,
    PlotCharacterization,
    PlotCharacterizationAuditEvent,
    PlotPlanting,
)


class CacaoVarietySerializer(serializers.ModelSerializer):
    class Meta:
        model = CacaoVariety
        fields = ["id", "name", "common_names", "description", "is_active"]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class CacaoVarietyListSerializer(serializers.Serializer):
    results = CacaoVarietySerializer(many=True)


class CacaoVarietyListQuerySerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)


def common_names_field(**kwargs):
    # Se repiten entre variedades a propósito (de un mismo lugar salen varios clones); dentro de
    # una variedad, el modelo quita los repetidos.
    return serializers.ListField(
        child=serializers.CharField(max_length=60),
        max_length=MAX_COMMON_NAMES,
        **kwargs,
    )


class CacaoVarietyCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=60)
    common_names = common_names_field(required=False)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CacaoVarietyUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=60, required=False)
    common_names = common_names_field(required=False)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


# --- Caracterización de parcelas ----------------------------------------------------------------

MAX_PLANTINGS = 10
MAX_TREES = 1_000_000
SELECT_VARIETY = "Seleccione la variedad de cacao."


class VarietyRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = CacaoVariety
        fields = ["id", "name", "is_active"]
        read_only_fields = fields


class PlantingSerializer(serializers.ModelSerializer):
    variety = VarietyRefSerializer()
    planting_date = PlantingMonthField()

    class Meta:
        model = PlotPlanting
        fields = ["variety", "planting_date", "tree_count", "propagation", "stage"]
        read_only_fields = fields


class PlotCharacterizationSerializer(serializers.ModelSerializer):
    plot_id = serializers.UUIDField(source="pk")
    plantings = PlantingSerializer(many=True)
    # La suma de las siembras. La edad media y la densidad no se envían: la edad cambia con el
    # tiempo y la densidad depende del área de la parcela, así que las calcula la interfaz.
    total_trees = serializers.SerializerMethodField()

    class Meta:
        model = PlotCharacterization
        fields = [
            "plot_id",
            "plantings",
            "total_trees",
            "management_system",
            "shade_type",
            "version",
            "captured_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_trees(self, characterization) -> int:
        # Desde las siembras ya cargadas, sin otra consulta.
        return sum(row.tree_count for row in characterization.plantings.all())


@extend_schema_serializer(many=False)
class PlotCharacterizationListSerializer(serializers.Serializer):
    results = PlotCharacterizationSerializer(many=True)


class PlotCharacterizationListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField()


class PlantingInputSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    variety_id = serializers.UUIDField()
    planting_date = PlantingMonthField()
    tree_count = serializers.IntegerField(min_value=1, max_value=MAX_TREES)
    propagation = serializers.ChoiceField(choices=Propagation.choices)
    stage = serializers.ChoiceField(choices=Stage.choices)


class PlotCharacterizationWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Obligatorio aunque admita `null`: `null` es "creo que la parcela no tiene ficha", y no
    # enviarlo sería no decir nada.
    expected_version = serializers.IntegerField(min_value=1, allow_null=True)
    # Sin siembras, o sin el campo, el mismo mensaje que muestra el formulario.
    plantings = PlantingInputSerializer(
        many=True, error_messages={"required": SELECT_VARIETY, "null": SELECT_VARIETY}
    )
    management_system = serializers.ChoiceField(
        choices=ManagementSystem.choices, allow_null=True, required=False, default=None
    )
    shade_type = serializers.ChoiceField(
        choices=ShadeType.choices, allow_null=True, required=False, default=None
    )
    # Hora del dispositivo, informativa: no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(allow_null=True, required=False, default=None)

    def validate_plantings(self, rows):
        if not rows:
            raise serializers.ValidationError(SELECT_VARIETY)
        if len(rows) > MAX_PLANTINGS:
            raise serializers.ValidationError(
                f"Una parcela admite hasta {MAX_PLANTINGS} siembras."
            )
        # La misma variedad en otra fecha es otra tanda; con la misma fecha, un repetido.
        keys = [(row["variety_id"], row["planting_date"]) for row in rows]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError("Esta siembra ya está en la lista.")
        return rows


class StaleCharacterizationErrorSerializer(ApiErrorSerializer):
    # Solo se documenta. `current` llega con `stale_version`: la ficha vigente, o `null` si la
    # parcela no tiene, para resolver el conflicto sin otra consulta.
    current = PlotCharacterizationSerializer(allow_null=True)


class SnapshotPlantingSerializer(serializers.Serializer):
    # Un comentario y no un docstring: aparecería como la descripción del componente.
    # Solo documenta la forma de lo que guarda el historial: no valida nada.
    variety_id = serializers.UUIDField()
    name = serializers.CharField()
    planting_date = serializers.CharField()
    tree_count = serializers.IntegerField()
    propagation = serializers.ChoiceField(choices=Propagation.choices)
    stage = serializers.ChoiceField(choices=Stage.choices)


class PlotCharacterizationSnapshotSerializer(serializers.Serializer):
    plantings = SnapshotPlantingSerializer(many=True)
    management_system = serializers.ChoiceField(choices=ManagementSystem.choices, allow_null=True)
    shade_type = serializers.ChoiceField(choices=ShadeType.choices, allow_null=True)


class PlotCharacterizationEventSerializer(serializers.ModelSerializer):
    # Una versión de la ficha en su historial, con los valores que dejó. Un comentario y no un
    # docstring: aparecería como la descripción del componente en el esquema.

    # El nombre de la cuenta (su correo si no tiene nombre), y solo lo ve quien ve la parcela:
    # el productor y su equipo. `null` si la cuenta se eliminó.
    actor_name = serializers.SerializerMethodField()
    changed_fields = serializers.ListField(child=serializers.CharField(), read_only=True)
    snapshot = serializers.SerializerMethodField()

    class Meta:
        model = PlotCharacterizationAuditEvent
        fields = ["version", "action", "occurred_at", "actor_name", "changed_fields", "snapshot"]
        read_only_fields = fields

    @extend_schema_field(PlotCharacterizationSnapshotSerializer)
    def get_snapshot(self, event) -> dict:
        # Tal como se guardó: es lo que dejó esa versión, y no se vuelve a interpretar.
        return event.snapshot

    def get_actor_name(self, event) -> str | None:
        return event.actor.get_full_name() or event.actor.email if event.actor else None
