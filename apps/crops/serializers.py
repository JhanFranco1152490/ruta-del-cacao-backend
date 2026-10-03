from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin

from .choices import ManagementSystem, ShadeType, Stage
from .fields import PlantingMonthField
from .models import CacaoVariety, PlotCharacterization, PlotCharacterizationVariety


class CacaoVarietySerializer(serializers.ModelSerializer):
    class Meta:
        model = CacaoVariety
        fields = ["id", "name", "description", "is_active"]
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


class CacaoVarietyCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=60)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CacaoVarietyUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=60, required=False)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


# --- Caracterización de parcelas ----------------------------------------------------------------

MAX_VARIETIES = 10
MAX_TREES = 1_000_000
SELECT_VARIETY = "Seleccione la variedad de cacao."


class VarietyRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = CacaoVariety
        fields = ["id", "name", "is_active"]
        read_only_fields = fields


class CharacterizationRowSerializer(serializers.ModelSerializer):
    variety = VarietyRefSerializer()

    class Meta:
        model = PlotCharacterizationVariety
        fields = ["variety", "tree_count"]
        read_only_fields = fields


class PlotCharacterizationSerializer(serializers.ModelSerializer):
    plot_id = serializers.UUIDField(source="pk")
    varieties = CharacterizationRowSerializer(many=True)
    # La suma de las filas. La edad y la densidad no se envían: la edad cambia con el tiempo y
    # la densidad depende del área de la parcela, así que las calcula la interfaz.
    total_trees = serializers.SerializerMethodField()
    planting_date = PlantingMonthField()

    class Meta:
        model = PlotCharacterization
        fields = [
            "plot_id",
            "varieties",
            "total_trees",
            "planting_date",
            "stage",
            "management_system",
            "shade_type",
            "version",
            "captured_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_trees(self, characterization) -> int:
        # Desde las filas ya cargadas, sin otra consulta.
        return sum(row.tree_count for row in characterization.varieties.all())


@extend_schema_serializer(many=False)
class PlotCharacterizationListSerializer(serializers.Serializer):
    results = PlotCharacterizationSerializer(many=True)


class PlotCharacterizationListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField()


class CharacterizationRowInputSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    variety_id = serializers.UUIDField()
    tree_count = serializers.IntegerField(min_value=1, max_value=MAX_TREES)


class PlotCharacterizationWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Obligatorio aunque admita `null`: `null` es "creo que la parcela no tiene ficha", y no
    # enviarlo sería no decir nada.
    expected_version = serializers.IntegerField(min_value=1, allow_null=True)
    # Sin filas, o sin el campo, el mismo mensaje que muestra el formulario.
    varieties = CharacterizationRowInputSerializer(
        many=True, error_messages={"required": SELECT_VARIETY, "null": SELECT_VARIETY}
    )
    planting_date = PlantingMonthField()
    stage = serializers.ChoiceField(choices=Stage.choices)
    management_system = serializers.ChoiceField(
        choices=ManagementSystem.choices, allow_null=True, required=False, default=None
    )
    shade_type = serializers.ChoiceField(
        choices=ShadeType.choices, allow_null=True, required=False, default=None
    )
    # Hora del dispositivo, informativa: no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(allow_null=True, required=False, default=None)

    def validate_varieties(self, rows):
        if not rows:
            raise serializers.ValidationError(SELECT_VARIETY)
        if len(rows) > MAX_VARIETIES:
            raise serializers.ValidationError(
                f"Una parcela admite hasta {MAX_VARIETIES} variedades."
            )
        ids = [row["variety_id"] for row in rows]
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError("Esta variedad ya está en la lista.")
        return rows


class StaleCharacterizationErrorSerializer(ApiErrorSerializer):
    # Solo se documenta. `current` llega con `stale_version`: la ficha vigente, o `null` si la
    # parcela no tiene, para resolver el conflicto sin otra consulta.
    current = PlotCharacterizationSerializer(allow_null=True)
