from rest_framework import serializers

from apps.common.contracts.audit_log import AUDIT_RECORD_TYPES


class AuditOptionsQuerySerializer(serializers.Serializer):
    # Solo lo usa la cuenta técnica, y para ella es obligatorio; las demás ven lo suyo.
    producer = serializers.UUIDField(required=False)


class AuditLogQuerySerializer(AuditOptionsQuerySerializer):
    actor = serializers.UUIDField(required=False)
    record_type = serializers.ChoiceField(choices=AUDIT_RECORD_TYPES, required=False)

    def get_fields(self):
        fields = super().get_fields()
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo. El periodo
        # es opcional: sin él, toda la bitácora.
        fields["from"] = serializers.DateField(required=False)
        fields["to"] = serializers.DateField(required=False)
        return fields

    def validate(self, attrs):
        if "from" in attrs and "to" in attrs and attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["Debe ser igual o posterior a `from`."]})
        return attrs
