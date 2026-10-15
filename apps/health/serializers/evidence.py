from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

# --- Evidencia ----------------------------------------------------------------------------------


class UploaderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, account) -> str:
        return account.get_full_name() or account.email


class EvidenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    file_name = serializers.CharField()
    content_type = serializers.CharField()
    size = serializers.IntegerField()
    # `null` si la cuenta que la subió se eliminó.
    uploaded_by = UploaderSerializer(allow_null=True)
    uploaded_at = serializers.DateTimeField()
    captured_at = serializers.DateTimeField(allow_null=True)


@extend_schema_serializer(many=False)
class EvidenceListSerializer(serializers.Serializer):
    results = EvidenceSerializer(many=True)


class EvidenceUploadSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el dispositivo: la foto espera en la cola y un reenvío no la duplica.
    id = serializers.UUIDField()
    # El formato y el tamaño los revisa el servicio, por el contenido y con su código de error.
    file = serializers.FileField(allow_empty_file=True)
    # Hora del dispositivo al tomarla; informativa.
    captured_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
