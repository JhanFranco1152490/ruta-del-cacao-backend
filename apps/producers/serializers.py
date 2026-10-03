from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin

from .models import PRODUCER_ROLE_CODE, Producer


class ProducerAccountSerializer(serializers.Serializer):
    # Un comentario y no un docstring (ver RejectUnknownFieldsMixin más abajo): drf-spectacular
    # lo tomaría como la descripción del componente. No es un `ModelSerializer` de `User` a
    # propósito: esta app no importa el modelo de otra.

    id = serializers.UUIDField()
    email = serializers.EmailField()
    status = serializers.CharField()
    activation_pending = serializers.BooleanField()


class ProducerSerializer(RejectUnknownFieldsMixin, serializers.ModelSerializer):
    account = serializers.SerializerMethodField()
    association_access = serializers.SerializerMethodField()
    # Opcional en el modelo (se puede vaciar al editar, ver ProducerUpdateSerializer), pero
    # obligatorio al crear: HU-03 crea la cuenta Productor con este correo en la misma
    # operación, y una cuenta exige correo.
    email = serializers.EmailField()

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
            "account",
            "association_access",
        ]
        read_only_fields = [
            "id",
            "member_code",
            "status",
            "version",
            "created_at",
            "updated_at",
            "account",
            "association_access",
        ]
        # Sin validador de unicidad previo: el duplicado lo decide la base de datos (409).
        validators = []

    def validate_email(self, value):
        return value.lower() if value else None

    def validate_phone(self, value):
        return value or None

    @extend_schema_field(ProducerAccountSerializer(allow_null=True))
    def get_account(self, producer) -> dict | None:
        # `_producer_account` lo deja get_producer() precargado (evita una consulta más); si
        # no está (por ejemplo, la respuesta de crear o editar), se busca aquí mismo, siempre
        # acotada por el id del productor, sin importar cuántas cuentas existan en total.
        accounts = getattr(producer, "_producer_account", None)
        if accounts is None:
            accounts = list(producer.accounts.filter(groups__role__code=PRODUCER_ROLE_CODE))
        if not accounts:
            return None
        user = accounts[0]
        return ProducerAccountSerializer(
            {
                "id": user.id,
                "email": user.email,
                "status": "active" if user.is_active else "inactive",
                "activation_pending": not user.has_usable_password(),
            }
        ).data

    def get_association_access(self, producer) -> bool:
        access = getattr(producer, "association_access", None)
        return bool(access and access.enabled)


class ProducerDetailSerializer(ProducerSerializer):
    email = serializers.EmailField(allow_null=True)


class ProducerUpdateSerializer(ProducerSerializer):
    # A diferencia de la creación, editar sí admite dejarlo vacío (la cuenta ya creada no
    # depende de que el expediente conserve un correo).
    email = serializers.EmailField(required=False, allow_null=True)
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


class ProducerDeleteSerializer(serializers.Serializer):
    # Query param del DELETE, con la versión leída: no se elimina un productor que otra persona
    # acaba de cambiar.
    expected_version = serializers.IntegerField(min_value=1)


class ProducerConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. La clave únicamente
    # llega cuando el conflicto es un documento repetido y la persona puede ver productores.
    existing_producer_id = serializers.UUIDField(required=False)
