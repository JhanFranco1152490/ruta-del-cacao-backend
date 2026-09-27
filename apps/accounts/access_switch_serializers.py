from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin


class AssociationAccessSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    changed_at = serializers.DateTimeField(allow_null=True)


class AssociationAccessUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    enabled = serializers.BooleanField()
