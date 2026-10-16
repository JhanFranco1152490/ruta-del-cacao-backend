from rest_framework import serializers

from apps.common.activity_representation import activity_serializer

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "severity", "created_at", "read_at", "condition_date"]
        read_only_fields = fields

    def get_fields(self):
        # La actividad con la misma forma del calendario, como está hoy: estado y días de
        # retraso calculados hoy. Se lee del registro común al armar los campos, porque la app
        # de actividades lo registra al arrancar.
        return {
            **super().get_fields(),
            "activity": activity_serializer()(read_only=True, allow_null=True),
        }


class InboxQuerySerializer(serializers.Serializer):
    unread = serializers.BooleanField(required=False, default=False)


class UnreadCountSerializer(serializers.Serializer):
    count = serializers.IntegerField()


class UpdatedCountSerializer(serializers.Serializer):
    updated = serializers.IntegerField()


class DismissedCountSerializer(serializers.Serializer):
    dismissed = serializers.IntegerField()
