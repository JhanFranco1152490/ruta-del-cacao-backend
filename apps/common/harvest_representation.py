"""Cómo se muestra una cosecha. La usan las cosechas y los lotes (que llevan su cosecha dentro),
y ninguna de las dos apps importa de la otra, así que vive aquí."""

from rest_framework import serializers

from .serializers import full_name


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


class HarvestRepresentationSerializer(serializers.Serializer):
    """La cosecha sin su lote. Solo de salida."""

    id = serializers.UUIDField()
    plot = HarvestPlotSerializer()
    producer_id = serializers.UUIDField(source="plot.farm.producer_id")
    harvest_date = serializers.DateField()
    green_weight_kg = serializers.DecimalField(max_digits=7, decimal_places=1)
    variety = HarvestVarietySerializer()
    collector = serializers.SerializerMethodField()
    characterization_version = serializers.IntegerField()
    registered_by = serializers.SerializerMethodField()
    captured_at = serializers.DateTimeField(allow_null=True)
    version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_collector(self, harvest) -> HarvestCollectorSerializer:
        account = harvest.collector
        return {"id": account.pk, "full_name": full_name(account), "is_active": account.is_active}

    def get_registered_by(self, harvest) -> HarvestRecorderSerializer(allow_null=True):
        account = harvest.registered_by
        return None if account is None else {"id": account.pk, "full_name": full_name(account)}
