from urllib.parse import urlsplit

from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from .models import PushSubscription

# Los servicios de push de los navegadores (Chrome y Edge en Android, Firefox, Safari y Edge en
# Windows). El servidor le hace una petición a la dirección que manda el navegador: con cualquier
# `https`, alguien podría hacer que el servidor llame a un sitio arbitrario, también uno interno.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)


def is_push_service(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == allowed or host.endswith(f".{allowed}") for allowed in PUSH_SERVICE_HOSTS
    )


class PushKeysSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=100)


class PushSubscriptionCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # La suscripción tal como la entrega el navegador, más un nombre del dispositivo.
    endpoint = serializers.CharField(max_length=2000)
    keys = PushKeysSerializer()
    device_label = serializers.CharField(
        max_length=60, required=False, allow_null=True, allow_blank=True
    )

    def validate_endpoint(self, value):
        if not is_push_service(value):
            raise serializers.ValidationError(
                "Debe ser la dirección de un servicio de push de un navegador."
            )
        return value


class PushSubscriptionRemoveSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    endpoint = serializers.CharField(max_length=2000)


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ["id", "device_label", "created_at"]
        read_only_fields = fields


class PushConfigSerializer(serializers.Serializer):
    # Nula si las push no están configuradas: la app no ofrece activarlas.
    public_key = serializers.CharField(allow_null=True)
