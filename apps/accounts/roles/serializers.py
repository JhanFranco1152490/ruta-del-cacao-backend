from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin

from ..models import Role


class RoleProducerSerializer(serializers.Serializer):
    # Un comentario y no un docstring (ver RejectUnknownFieldsMixin en apps/common/serializers.py):
    # drf-spectacular lo tomaría como la descripción del componente. No es un `ModelSerializer`
    # de `Producer` a propósito: esta app no importa el modelo de otra.

    id = serializers.UUIDField()
    member_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class RolePermissionSerializer(serializers.Serializer):
    # Un comentario y no un docstring: ver RoleProducerSerializer.
    code = serializers.CharField()
    name = serializers.CharField()


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    permission_details = serializers.SerializerMethodField()
    producer = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "kind",
            "name",
            "description",
            "producer_id",
            "producer",
            "permissions",
            "permission_details",
        ]
        read_only_fields = fields

    def get_permissions(self, role) -> list[str]:
        return sorted(role.permission_codes)

    # Los permisos no delegables (los de la asociación) no están en `/api/permissions`, que solo
    # alimenta el formulario de roles propios: sin el nombre aquí, el detalle de un rol del sistema
    # mostraría el código. Mismo orden que `permissions`.
    @extend_schema_field(RolePermissionSerializer(many=True))
    def get_permission_details(self, role) -> list[dict]:
        names = role.permission_names
        return [{"code": code, "name": names[code]} for code in sorted(names)]

    @extend_schema_field(RoleProducerSerializer(allow_null=True))
    def get_producer(self, role) -> dict | None:
        # Agrupar los roles propios por productor en el frontend exige más que el id: el
        # nombre visible del dueño. `visible_roles()` ya precarga `producer` (select_related).
        if role.producer_id is None:
            return None
        return RoleProducerSerializer(role.producer).data


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
    requires = serializers.CharField(allow_null=True)


class PermissionListSerializer(serializers.Serializer):
    results = PermissionSerializer(many=True)
