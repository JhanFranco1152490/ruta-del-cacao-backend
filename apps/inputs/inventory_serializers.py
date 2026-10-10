from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from .models import NOTE_MAX_LENGTH, InputMovement, InputStock

QUANTITY_FIELD = {"max_digits": 12, "decimal_places": 3}


class InputStockSerializer(serializers.ModelSerializer):
    input_id = serializers.UUIDField(read_only=True)
    farm_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = InputStock
        fields = ["input_id", "farm_id", "quantity", "last_count_date", "updated_at"]
        read_only_fields = fields


# Sin `many=False`, el esquema envolvería la respuesta de una acción `list` en un arreglo, y
# esta respuesta es un solo objeto con `results`, sin paginar.
@extend_schema_serializer(many=False)
class InputStockListSerializer(serializers.Serializer):
    results = InputStockSerializer(many=True)


class InputMovementSerializer(serializers.ModelSerializer):
    # El nombre de la cuenta (su correo si no tiene nombre). `null` si la cuenta se eliminó.
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = InputMovement
        fields = [
            "id",
            "kind",
            "quantity",
            "counted_quantity",
            "occurred_on",
            "note",
            "actor_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, movement) -> str | None:
        actor = movement.actor
        return (actor.get_full_name() or actor.email) if actor else None


class InputMovementCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el cliente: reenviar la misma petición no duplica el movimiento.
    id = serializers.UUIDField(required=False)
    input_id = serializers.UUIDField()
    farm_id = serializers.UUIDField()
    # Las salidas por actividad las registra el sistema: no se aceptan aquí.
    kind = serializers.ChoiceField(
        choices=[(InputMovement.Kind.ENTRY, "Entrada"), (InputMovement.Kind.COUNT, "Conteo")]
    )
    quantity = serializers.DecimalField(required=False, **QUANTITY_FIELD)
    counted_quantity = serializers.DecimalField(required=False, **QUANTITY_FIELD)
    occurred_on = serializers.DateField()
    note = serializers.CharField(
        required=False, allow_blank=True, max_length=NOTE_MAX_LENGTH, default=""
    )


class InputMovementResultSerializer(serializers.Serializer):
    movement = InputMovementSerializer()
    stock = InputStockSerializer()


class InputStockQuerySerializer(serializers.Serializer):
    # Sin finca son las de todas las fincas del alcance. `producer` solo lo usa la cuenta técnica.
    farm = serializers.UUIDField(required=False)
    producer = serializers.UUIDField(required=False)


class InputMovementQuerySerializer(serializers.Serializer):
    input = serializers.UUIDField()
    farm = serializers.UUIDField()
