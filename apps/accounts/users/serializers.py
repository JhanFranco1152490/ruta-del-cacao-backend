from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.choices import DocumentType
from apps.common.serializers import RejectUnknownFieldsMixin, RequireSomeFieldMixin

from ..access import roles_of
from ..models import User
from ..system_roles import PRODUCER
from .farm_assignment import needs_farm


class AccountProducerSerializer(serializers.Serializer):
    # Un comentario y no un docstring (ver RejectUnknownFieldsMixin en apps/common/serializers.py):
    # drf-spectacular lo tomaría como la descripción del componente. No es un `ModelSerializer`
    # de `Producer` a propósito: esta app no importa el modelo de otra.

    id = serializers.UUIDField()
    member_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    status = serializers.CharField()
    municipality_code = serializers.CharField()


class AccountRoleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField(allow_null=True)
    name = serializers.CharField()


class AccountFarmSerializer(serializers.Serializer):
    # Una finca en la que trabaja un empleado. Tampoco es un `ModelSerializer`, por lo mismo.

    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class AccountSerializer(serializers.ModelSerializer):
    producer = AccountProducerSerializer(read_only=True, allow_null=True)
    farms = AccountFarmSerializer(many=True, read_only=True)
    # Un empleado con permisos de campo y sin finca no alcanza nada: la interfaz lo señala para
    # que el productor le asigne alguna.
    needs_farm = serializers.SerializerMethodField()
    # Que la cuenta alcanza todas las fincas de su productor: la del Productor, o la de un empleado
    # a quien se le dio «todas las fincas».
    all_farms = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    activation_pending = serializers.SerializerMethodField()
    has_signed_in = serializers.SerializerMethodField()
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
            "farms",
            "needs_farm",
            "all_farms",
            "roles",
            "status",
            "activation_pending",
            "has_signed_in",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(AccountRoleSerializer(many=True))
    def get_roles(self, user) -> list[dict]:
        # `group.role` (uno a uno inverso) ya viene precargado por `_optimized()`: no es una
        # consulta nueva por cada fila de la lista.
        return AccountRoleSerializer(roles_of(user), many=True).data

    def get_needs_farm(self, user) -> bool:
        return needs_farm(user)

    def get_all_farms(self, user) -> bool:
        # Con los grupos ya precargados de la lista: nada de una consulta por fila.
        return user.all_farms or any(role.code == PRODUCER for role in roles_of(user))

    def get_status(self, user) -> str:
        return "active" if user.is_active else "inactive"

    def get_activation_pending(self, user) -> bool:
        return not user.has_usable_password()

    def get_has_signed_in(self, user) -> bool:
        return user.last_login is not None


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
    # El alcance de un empleado: las fincas en las que trabaja, o todas. Una de las dos es
    # obligatoria, y debe cumplir lo que piden sus roles.
    farm_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    all_farms = serializers.BooleanField(required=False)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        return value or None


class AccountUpdateSerializer(
    RequireSomeFieldMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    # Reemplaza el alcance: las fincas, o todas. Una cuenta sin ninguno de los dos no se guarda.
    farm_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    all_farms = serializers.BooleanField(required=False)
    email = serializers.EmailField(max_length=254, required=False)
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    identity_document = serializers.CharField(max_length=50, required=False, trim_whitespace=True)
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True, allow_null=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        return value or None


class AccountRoleIdsSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    role_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    # Para dar el alcance en la misma operación en que los roles nuevos lo exigen.
    farm_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    all_farms = serializers.BooleanField(required=False)


class AccountStatusSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Mismos valor y etiqueta que Producer.Status (HU-02): así drf-spectacular fusiona los dos
    # enums de "status" del esquema en vez de generar uno duplicado con un nombre automático.
    status = serializers.ChoiceField(choices=[("active", "Activo"), ("inactive", "Inactivo")])


class ActivationEmailSentSerializer(serializers.Serializer):
    activation_email_sent = serializers.BooleanField()
