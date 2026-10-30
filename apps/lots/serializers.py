from rest_framework import serializers

from apps.common.contracts.harvest_representation import (
    HarvestRecorderSerializer,
    HarvestRepresentationSerializer,
)
from apps.common.contracts.lot_details import lot_detail_fields, lot_detail_prefetch
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

    def get_fields(self):
        # Lo que otras apps agregan (la fermentación, el secado). Se suma aquí y no en la clase
        # porque esas apps se registran después de que esta se importa.
        return {**super().get_fields(), **lot_detail_fields()}

    def get_producer(self, lot) -> LotProducerSerializer:
        producer = lot.harvest.plot.farm.producer
        return {"id": producer.pk, "member_code": producer.member_code}

    def get_created_by(self, lot) -> HarvestRecorderSerializer(allow_null=True):
        account = lot.created_by
        return None if account is None else {"id": account.pk, "full_name": full_name(account)}


class LotFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class LotBriefSerializer(serializers.Serializer):
    # Un lote nombrado desde otra app (un aviso): su código, su estado, su finca y la etapa en que
    # está, sin su cosecha completa.
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LotStatus.choices)
    farm = LotFarmSerializer(source="harvest.plot.farm")

    def get_fields(self):
        # Como en `LotSerializer`: la fermentación y el secado, con su cajón o su marquesina.
        return {**super().get_fields(), **lot_detail_fields()}


def lot_brief_prefetch() -> list[str]:
    return ["harvest__plot__farm", *lot_detail_prefetch()]


class LotCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el dispositivo, para que un reenvío no cree otro lote; si no llega, lo genera el
    # servidor.
    id = serializers.UUIDField(required=False)
    harvest_id = serializers.UUIDField()


class LotListQuerySerializer(serializers.Serializer):
    # Los filtros del listado paginado; `page` y `page_size` los lee la paginación.
    status = serializers.ChoiceField(choices=LotStatus.choices, required=False)
    farm = serializers.UUIDField(required=False)
    plot = serializers.UUIDField(required=False)
    variety = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=40)
    producer = serializers.UUIDField(required=False)

    def get_fields(self):
        fields = super().get_fields()
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo.
        fields["from"] = serializers.DateField(required=False)
        fields["to"] = serializers.DateField(required=False)
        return fields

    def validate(self, attrs):
        if "from" in attrs and "to" in attrs and attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["Debe ser igual o posterior a `from`."]})
        return attrs


class LotSummaryQuerySerializer(LotListQuerySerializer):
    # Los mismos filtros de la lista menos el estado, que es lo que se cuenta.
    def get_fields(self):
        fields = super().get_fields()
        fields.pop("status")
        return fields


class LotStatusTotalSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LotStatus.choices)
    count = serializers.IntegerField()
    green_weight_kg = serializers.DecimalField(max_digits=12, decimal_places=1)


class LotSummarySerializer(serializers.Serializer):
    results = LotStatusTotalSerializer(many=True)


class LotDeleteQuerySerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class LotConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `harvest_already_in_lot` (el lote que ya existe) y con `stale_version`.
    current = LotSerializer(required=False)
    current_status = serializers.CharField(required=False)
