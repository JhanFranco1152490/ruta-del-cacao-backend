from datetime import datetime
from zoneinfo import ZoneInfo

from rest_framework import serializers

from .contacts import InvalidPhoneNumber, normalize_phone
from .documents import (
    InvalidIdentityDocument,
    normalize_document_type,
    normalize_identity_document,
)
from .models import Producer
from .municipalities import InvalidMunicipalityCode, validate_municipality_code


class StrictFieldsSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        unknown_fields = set(data.keys()) - set(self.fields)
        if unknown_fields:
            raise serializers.ValidationError(
                {field_name: ["Campo no permitido."] for field_name in sorted(unknown_fields)}
            )
        return super().to_internal_value(data)


class ProducerFieldsSerializer(StrictFieldsSerializer):
    document_type = serializers.CharField(max_length=3, required=False)
    identity_document = serializers.CharField(max_length=15, required=False, trim_whitespace=True)
    first_name = serializers.CharField(max_length=100, required=False, trim_whitespace=True)
    last_name = serializers.CharField(max_length=100, required=False, trim_whitespace=True)
    phone = serializers.CharField(max_length=25, required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(
        max_length=254, required=False, allow_blank=True, allow_null=True
    )
    municipality_code = serializers.CharField(max_length=20, required=False, trim_whitespace=True)
    joined_on = serializers.DateField(required=False)

    def validate(self, attrs):
        if "document_type" in attrs:
            try:
                attrs["document_type"] = normalize_document_type(attrs["document_type"])
            except InvalidIdentityDocument as error:
                raise serializers.ValidationError({"document_type": str(error)}) from error
        if "identity_document" in attrs:
            try:
                attrs["identity_document"] = normalize_identity_document(
                    attrs["identity_document"]
                )
            except InvalidIdentityDocument as error:
                raise serializers.ValidationError({"identity_document": str(error)}) from error
        if "phone" in attrs:
            try:
                attrs["phone"] = normalize_phone(attrs["phone"])
            except InvalidPhoneNumber as error:
                raise serializers.ValidationError({"phone": str(error)}) from error
        if "municipality_code" in attrs:
            try:
                attrs["municipality_code"] = validate_municipality_code(attrs["municipality_code"])
            except InvalidMunicipalityCode as error:
                raise serializers.ValidationError({"municipality_code": str(error)}) from error
        if "email" in attrs and attrs["email"] is not None:
            attrs["email"] = attrs["email"].strip().lower() or None
        if (
            "joined_on" in attrs
            and attrs["joined_on"] > datetime.now(ZoneInfo("America/Bogota")).date()
        ):
            raise serializers.ValidationError({"joined_on": "La fecha no puede ser futura."})
        return attrs


class ProducerCreateSerializer(ProducerFieldsSerializer):
    document_type = serializers.CharField(max_length=3, required=True)
    identity_document = serializers.CharField(max_length=15, required=True, trim_whitespace=True)
    first_name = serializers.CharField(max_length=100, required=True, trim_whitespace=True)
    last_name = serializers.CharField(max_length=100, required=True, trim_whitespace=True)
    municipality_code = serializers.CharField(max_length=20, required=True, trim_whitespace=True)
    joined_on = serializers.DateField(required=True)


class ProducerUpdateSerializer(ProducerFieldsSerializer):
    expected_version = serializers.IntegerField(min_value=1, required=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class ProducerStatusSerializer(StrictFieldsSerializer):
    status = serializers.ChoiceField(choices=Producer.Status.values)
    expected_version = serializers.IntegerField(min_value=1)


class ProducerListQuerySerializer(StrictFieldsSerializer):
    search = serializers.CharField(max_length=100, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Producer.Status.values, required=False)
    municipality_code = serializers.CharField(max_length=20, required=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)
