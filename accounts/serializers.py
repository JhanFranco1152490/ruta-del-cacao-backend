from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=256, trim_whitespace=True, write_only=True)
    new_password = serializers.CharField(
        min_length=15,
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    new_password_confirmation = serializers.CharField(
        min_length=15,
        max_length=128,
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
