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


MAX_PERIOD_DAYS = 92


class HarvestListQuerySerializer(serializers.Serializer):
    # Un mes por petición es lo habitual (la copia del dispositivo es por mes); 92 días dejan pedir
    # un trimestre sin abrir la puerta a años enteros sin paginar.

    def get_fields(self):
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo.
        return {
            "from": serializers.DateField(),
            "to": serializers.DateField(),
            "farm": serializers.UUIDField(required=False),
            "plot": serializers.UUIDField(required=False),
            "producer": serializers.UUIDField(required=False),
        }

    def validate(self, attrs):
        if attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["Debe ser igual o posterior a `from`."]})
        if (attrs["to"] - attrs["from"]).days + 1 > MAX_PERIOD_DAYS:
            raise serializers.ValidationError(
                {"to": [f"El periodo no puede pasar de {MAX_PERIOD_DAYS} días."]}
            )
        return attrs


class HarvestListSerializer(serializers.Serializer):
    results = HarvestSerializer(many=True)


class CollectorQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class CollectorOptionSerializer(serializers.Serializer):
    # Una cuenta de la lista de recolectores. `farm_ids` son las fincas en las que trabaja (vacía
    # en el Productor y en quien trabaja en todas) y `assignable`, si quien pregunta puede
    # nombrarla recolectora.
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()
    farm_ids = serializers.ListField(child=serializers.UUIDField())
    all_farms = serializers.BooleanField()
    assignable = serializers.BooleanField()


class CollectorListSerializer(serializers.Serializer):
    results = CollectorOptionSerializer(many=True)
