from rest_framework import serializers

from apps.common.contracts.activity_representation import activity_serializer
from apps.common.contracts.lot_representation import lot_brief_serializer

from .models import Notification

# El volteo y la bitácora se toman de la relación y no de su app: ninguna app importa de otra.
FermentationTurn = Notification._meta.get_field("fermentation_turn").related_model
DryingLogEntry = Notification._meta.get_field("drying_log").related_model


class NotificationTurnSerializer(serializers.ModelSerializer):
    # La posición del volteo por hora en su fermentación: la calcula la consulta de la bandeja.
    number = serializers.IntegerField()

    class Meta:
        model = FermentationTurn
        fields = ["id", "number", "turned_at", "temperature_c", "ph"]
        read_only_fields = fields


class NotificationDryingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DryingLogEntry
        fields = ["id", "day_number", "measured_at", "moisture_pct"]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    # El volteo y la bitácora de un desvío, como están ahora: si se corrigieron, el valor
    # corregido, que es el que importa.
    fermentation_turn = NotificationTurnSerializer(read_only=True, allow_null=True)
    drying_log = NotificationDryingLogSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Notification
        # `detection_id` solo en el control pendiente: la detección con sus controles viene
        # dentro de `activity.monitoring`, y el dispositivo la busca ahí por su id.
        fields = [
            "id",
            "kind",
            "severity",
            "created_at",
            "read_at",
            "condition_date",
            "condition_at",
            "resolved_at",
            "detection_id",
            "fermentation_turn",
            "drying_log",
        ]
        read_only_fields = fields

    def get_fields(self):
        # La actividad con la misma forma del calendario, como está hoy: estado y días de
        # retraso calculados hoy. El lote, nombrado como lo nombra su app, con la etapa en que
        # está. Se leen del registro común al armar los campos, porque esas apps lo registran al
        # arrancar.
        return {
            **super().get_fields(),
            "activity": activity_serializer()(read_only=True, allow_null=True),
            "lot": lot_brief_serializer()(read_only=True, allow_null=True),
        }


class InboxQuerySerializer(serializers.Serializer):
    unread = serializers.BooleanField(required=False, default=False)


class UnreadCountSerializer(serializers.Serializer):
    count = serializers.IntegerField()


class UpdatedCountSerializer(serializers.Serializer):
    updated = serializers.IntegerField()


class DismissedCountSerializer(serializers.Serializer):
    dismissed = serializers.IntegerField()
