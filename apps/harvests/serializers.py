from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin, full_name

from .models import Harvest


class HarvestFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class HarvestPlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    farm = HarvestFarmSerializer()


class HarvestVarietySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class HarvestCollectorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()


class HarvestRecorderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()


class HarvestLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.CharField()


class HarvestSerializer(serializers.ModelSerializer):
    plot = HarvestPlotSerializer()
    producer_id = serializers.UUIDField(source="plot.farm.producer_id")
    variety = HarvestVarietySerializer()
    collector = serializers.SerializerMethodField()
    registered_by = serializers.SerializerMethodField()
    lot = serializers.SerializerMethodField()

    class Meta:
        model = Harvest
        fields = [
            "id",
            "plot",
            "producer_id",
            "harvest_date",
            "green_weight_kg",
            "variety",
            "collector",
            "characterization_version",
            "lot",
            "registered_by",
            "captured_at",
            "version",
            "created_at",
            "updated_at",
        ]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields

    def get_collector(self, harvest) -> HarvestCollectorSerializer:
        account = harvest.collector
        return {"id": account.pk, "full_name": full_name(account), "is_active": account.is_active}

    def get_registered_by(self, harvest) -> HarvestRecorderSerializer(allow_null=True):
        account = harvest.registered_by
        return None if account is None else {"id": account.pk, "full_name": full_name(account)}

    def get_lot(self, harvest) -> HarvestLotSerializer(allow_null=True):
        # El lote se alcanza por la relación inversa, sin importar la app que lo define. Mientras
        # la cosecha no forma un lote, la relación no tiene fila.
        lot = getattr(harvest, "lot", None)
        if lot is None:
            return None
        return {"id": lot.pk, "code": lot.code, "status": lot.status}


class HarvestCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Lo genera el dispositivo, para que un reenvío no duplique; si no llega, lo genera el
    # servidor.
    id = serializers.UUIDField(required=False)
    plot_id = serializers.UUIDField()
    harvest_date = serializers.DateField()
    # Báscula de campo: un decimal. Que sea mayor que cero y no pase del límite de la parcela lo
    # valida el servicio, con su mensaje.
    green_weight_kg = serializers.DecimalField(max_digits=7, decimal_places=1)
    variety_id = serializers.UUIDField()
    collector_id = serializers.UUIDField()
    # Hora del dispositivo al capturar; informativa, así que no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(required=False, allow_null=True)


class HarvestConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version`.
    current = HarvestSerializer(required=False)
