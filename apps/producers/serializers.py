from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin

from .models import Producer


class ProducerSerializer(RejectUnknownFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Producer
        fields = [
            "id",
            "member_code",
            "document_type",
            "identity_document",
            "first_name",
            "last_name",
            "phone",
            "email",
            "municipality_code",
            "joined_on",
            "status",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "member_code", "status", "version", "created_at", "updated_at"]
        # Sin validador de unicidad previo: el duplicado lo decide la base de datos (409).
        validators = []

    def validate_email(self, value):
        return value.lower() if value else None

    def validate_phone(self, value):
        return value or None


class ProducerUpdateSerializer(ProducerSerializer):
    expected_version = serializers.IntegerField(min_value=1, write_only=True)

    class Meta(ProducerSerializer.Meta):
        fields = [*ProducerSerializer.Meta.fields, "expected_version"]

    def validate(self, attrs):
        # Con partial=True ningún campo es obligatorio, ni siquiera la versión.
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class ProducerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producer
        fields = [
            "id",
            "member_code",
            "document_type",
            "identity_document",
            "first_name",
            "last_name",
            "municipality_code",
            "status",
        ]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields


class ProducerStatusSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    status = serializers.ChoiceField(choices=Producer.Status.choices)
    expected_version = serializers.IntegerField(min_value=1)


class ProducerConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. La clave únicamente
    # llega cuando el conflicto es un documento repetido y la persona puede ver productores.
    existing_producer_id = serializers.UUIDField(required=False)
