from rest_framework import serializers

from apps.common.harvest_representation import (
    HarvestRecorderSerializer,
    HarvestRepresentationSerializer,
)
from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin, full_name

from .choices import LotStatus


class LotProducerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_code = serializers.CharField()


class LotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LotStatus.choices)
    # La cosecha completa, sin su campo `lot`.
    harvest = HarvestRepresentationSerializer()
    producer = serializers.SerializerMethodField()
    # El de su cosecha: no se guarda dos veces.
    green_weight_kg = serializers.DecimalField(
        source="harvest.green_weight_kg", max_digits=7, decimal_places=1
    )
    created_by = serializers.SerializerMethodField()
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_producer(self, lot) -> LotProducerSerializer:
        producer = lot.harvest.plot.farm.producer
        return {"id": producer.pk, "member_code": producer.member_code}

    def get_created_by(self, lot) -> HarvestRecorderSerializer(allow_null=True):
        account = lot.created_by
        return None if account is None else {"id": account.pk, "full_name": full_name(account)}


class LotCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el dispositivo, para que un reenvío no cree otro lote; si no llega, lo genera el
    # servidor.
    id = serializers.UUIDField(required=False)
    harvest_id = serializers.UUIDField()


class LotConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `harvest_already_in_lot` (el lote que ya existe) y con `stale_version`.
    current = LotSerializer(required=False)
    current_status = serializers.CharField(required=False)
