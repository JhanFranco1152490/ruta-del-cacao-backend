from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from .models import Role


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "code", "kind", "name", "description", "producer_id", "permissions"]
        read_only_fields = fields

    def get_permissions(self, role) -> list[str]:
        return sorted(role.permission_codes)


class RoleCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    permission_codes = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, default=list
    )
    # Solo lo envía el Administrador; los demás actores lo sacan de su propia cuenta.
    producer_id = serializers.UUIDField(required=False)


class RoleUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    permission_codes = serializers.ListField(child=serializers.CharField(), required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class PermissionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    area = serializers.CharField()
    delegable = serializers.BooleanField()
    grantable = serializers.BooleanField()


class PermissionListSerializer(serializers.Serializer):
    results = PermissionSerializer(many=True)
