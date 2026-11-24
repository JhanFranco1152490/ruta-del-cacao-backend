from rest_framework import serializers

from apps.common.contracts.audit_log import (
    AUDIT_RECORD_TYPES,
    HIDDEN_REASONS,
    KINDS,
    RECORD_TYPE_LABELS,
)


class AuditChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.ChoiceField(choices=KINDS)
    # Texto, número, fecha o verdadero/falso según `kind`; nulo si `hidden` dice por qué.
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)
    hidden = serializers.ChoiceField(choices=HIDDEN_REASONS, allow_null=True)


class AuditActorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


class AuditRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="record_id", allow_null=True)
    label = serializers.CharField(source="record_label")
    deleted = serializers.BooleanField(source="record_deleted")


class AuditEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    actor = serializers.SerializerMethodField()
    record_type = serializers.ChoiceField(choices=AUDIT_RECORD_TYPES)
    record_type_label = serializers.SerializerMethodField()
    record = AuditRecordSerializer(source="*")
    action = serializers.CharField()
    action_label = serializers.CharField()
    changes = AuditChangeSerializer(many=True)

    def get_actor(self, entry) -> AuditActorSerializer(allow_null=True):
        # Sin la cuenta (se eliminó), sin autor: el frontend dice «Cuenta eliminada».
        if entry.actor_id is None or entry.actor_name is None:
            return None
        return AuditActorSerializer({"id": entry.actor_id, "full_name": entry.actor_name}).data

    def get_record_type_label(self, entry) -> str:
        return RECORD_TYPE_LABELS[entry.record_type]


class AuditOptionActorSerializer(AuditActorSerializer):
    is_active = serializers.BooleanField()


class AuditRecordTypeOptionSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=AUDIT_RECORD_TYPES)
    label = serializers.CharField()


class AuditOptionsSerializer(serializers.Serializer):
    actors = AuditOptionActorSerializer(many=True)
    record_types = AuditRecordTypeOptionSerializer(many=True)
