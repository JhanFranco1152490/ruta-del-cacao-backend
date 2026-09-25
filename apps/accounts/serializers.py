from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.common.choices import DocumentType
from apps.common.validators import strip_document_separators, validate_document_digits


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


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=256, trim_whitespace=True, write_only=True)
    new_password = serializers.CharField(
        min_length=8,
        max_length=50,
        trim_whitespace=False,
        write_only=True,
    )
    new_password_confirmation = serializers.CharField(
        min_length=8,
        max_length=50,
        trim_whitespace=False,
        write_only=True,
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirmation"]:
            raise serializers.ValidationError(
                {"new_password_confirmation": "Las contraseñas no coinciden."}
            )
        return attrs

    def validate_password_for_user(self, user):
        try:
            validate_password(self.validated_data["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": list(error.messages)}) from error
