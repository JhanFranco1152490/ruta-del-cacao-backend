from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.common.choices import DocumentType
from apps.common.validators import strip_document_separators, validate_document_digits

from .activation import user_from_activation_link
from .models import User
from .services import user_from_reset_link


class LoginSerializer(serializers.Serializer):
    login_method = serializers.ChoiceField(choices=["email", "document"])
    email = serializers.EmailField(required=False)
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    identity_document = serializers.CharField(max_length=50, required=False, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        if attrs["login_method"] == "email":
            if (
                not attrs.get("email")
                or attrs.get("document_type")
                or attrs.get("identity_document")
            ):
                raise serializers.ValidationError("El modo correo requiere únicamente email.")
        elif (
            not attrs.get("document_type")
            or not attrs.get("identity_document")
            or attrs.get("email")
        ):
            raise serializers.ValidationError("El modo documento requiere tipo y número.")
        if attrs.get("identity_document"):
            attrs["identity_document"] = strip_document_separators(attrs["identity_document"])
            try:
                validate_document_digits(attrs["identity_document"])
            except DjangoValidationError as error:
                raise serializers.ValidationError({"identity_document": error.messages}) from error
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class NewPasswordSerializer(serializers.Serializer):
    # Un comentario y no un docstring: drf-spectacular lo tomaría como la descripción del
    # componente generado y publicaría este texto interno en los tipos del cliente. Campos y
    # validación de la contraseña nueva, compartidos por recuperación y activación.

    new_password = serializers.CharField(
        min_length=8, max_length=50, trim_whitespace=False, write_only=True
    )
    new_password_confirmation = serializers.CharField(
        min_length=8, max_length=50, trim_whitespace=False, write_only=True
    )

    def validate_new_password_against(self, user, attrs):
        if attrs["new_password"] != attrs["new_password_confirmation"]:
            raise serializers.ValidationError(
                {"new_password_confirmation": "Las contraseñas no coinciden."}
            )
        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": list(error.messages)}) from error


class PasswordResetConfirmSerializer(NewPasswordSerializer):
    uid = serializers.CharField(max_length=64, write_only=True)
    token = serializers.CharField(max_length=128, write_only=True)

    def validate(self, attrs):
        user = user_from_reset_link(attrs["uid"], attrs["token"])
        self.validate_new_password_against(user, attrs)
        attrs["user"] = user
        return attrs


class ActivationConfirmSerializer(NewPasswordSerializer):
    uid = serializers.CharField(max_length=64, write_only=True)
    token = serializers.CharField(max_length=128, write_only=True)

    def validate(self, attrs):
        user = user_from_activation_link(attrs["uid"], attrs["token"])
        self.validate_new_password_against(user, attrs)
        attrs["user"] = user
        return attrs


class SessionUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "roles", "permissions"]

    def get_roles(self, user) -> list[str]:
        return list(user.groups.order_by("name").values_list("name", flat=True))

    def get_permissions(self, user) -> list[str]:
        return sorted(user.get_all_permissions())


class SessionSerializer(serializers.Serializer):
    user = SessionUserSerializer()


class CsrfTokenSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()
