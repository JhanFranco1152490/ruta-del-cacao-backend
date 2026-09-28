from rest_framework import serializers

from apps.common.choices import DocumentType
from apps.common.serializers import RejectUnknownFieldsMixin

from .access import roles_of
from .models import User


class AccountProducerSerializer(serializers.Serializer):
    # Un comentario y no un docstring (ver RejectUnknownFieldsMixin en apps/common/serializers.py):
    # drf-spectacular lo tomaría como la descripción del componente. No es un `ModelSerializer`
    # de `Producer` a propósito: esta app no importa el modelo de otra.

    id = serializers.UUIDField()
    member_code = serializers.CharField()
    status = serializers.CharField()


class AccountRoleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField(allow_null=True)
    name = serializers.CharField()


class AccountSerializer(serializers.ModelSerializer):
    producer = AccountProducerSerializer(read_only=True, allow_null=True)
    roles = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    activation_pending = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "document_type",
            "identity_document",
            "phone",
            "producer",
            "roles",
            "status",
            "activation_pending",
            "created_at",
        ]
        read_only_fields = fields

    def get_roles(self, user) -> list[dict]:
        # `group.role` (uno a uno inverso) ya viene precargado por `_optimized()`: no es una
        # consulta nueva por cada fila de la lista.
        return AccountRoleSerializer(roles_of(user), many=True).data

    def get_status(self, user) -> str:
        return "active" if user.is_active else "inactive"

    def get_activation_pending(self, user) -> bool:
        return not user.has_usable_password()


class AccountCreatedSerializer(AccountSerializer):
    # Documenta la respuesta del alta: la cuenta más si el correo de activación se envió.
    activation_email_sent = serializers.BooleanField(read_only=True)

    class Meta(AccountSerializer.Meta):
        fields = [*AccountSerializer.Meta.fields, "activation_email_sent"]
        read_only_fields = fields


class AccountCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    identity_document = serializers.CharField(max_length=50, required=False, trim_whitespace=True)
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True, allow_null=True)
    role_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    # Solo lo envía el Administrador; los demás actores lo sacan de su propia cuenta o del
    # expediente del productor (ver create_account en user_services.py).
    producer_id = serializers.UUIDField(required=False)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        return value or None


class AccountUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    email = serializers.EmailField(max_length=254, required=False)
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    identity_document = serializers.CharField(max_length=50, required=False, trim_whitespace=True)
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        return value or None


class AccountRoleIdsSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    role_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


class AccountStatusSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Mismos valor y etiqueta que Producer.Status (HU-02): así drf-spectacular fusiona los dos
    # enums de "status" del esquema en vez de generar uno duplicado con un nombre automático.
    status = serializers.ChoiceField(choices=[("active", "Activo"), ("inactive", "Inactivo")])


class ActivationEmailSentSerializer(serializers.Serializer):
    activation_email_sent = serializers.BooleanField()
