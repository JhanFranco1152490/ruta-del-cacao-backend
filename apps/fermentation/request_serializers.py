"""Lo que la API de fermentación recibe: el cuerpo y los parámetros de cada petición. Lo que
responde está en `serializers.py`."""

from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from .models import MAX_PH, MAX_TEMPERATURE_C, NOTES_MAX_LENGTH


class StartOptionsQuerySerializer(serializers.Serializer):
    lot = serializers.UUIDField()


class FermentationListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField(required=False)
    producer = serializers.UUIDField(required=False)


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


class FermentationFinishSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    ended_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH, allow_blank=True, required=False)


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
