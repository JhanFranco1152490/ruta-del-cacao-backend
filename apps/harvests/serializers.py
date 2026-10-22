from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.common.contracts.harvest_representation import HarvestRepresentationSerializer
from apps.common.serializers import (
    ApiErrorSerializer,
    PeriodQuerySerializer,
    RejectUnknownFieldsMixin,
    RequireVersionedChangeMixin,
)


class HarvestLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.CharField()


class HarvestSerializer(HarvestRepresentationSerializer):
    lot = serializers.SerializerMethodField()

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


class HarvestUpdateSerializer(
    RequireVersionedChangeMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    # La parcela no está: una cosecha no cambia de parcela.
    harvest_date = serializers.DateField(required=False)
    green_weight_kg = serializers.DecimalField(max_digits=7, decimal_places=1, required=False)
    variety_id = serializers.UUIDField(required=False)
    collector_id = serializers.UUIDField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class HarvestDeleteQuerySerializer(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class HarvestConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version`.
    current = HarvestSerializer(required=False)


class HarvestListQuerySerializer(PeriodQuerySerializer):
    # Un mes por petición es lo habitual (la copia del dispositivo es por mes); 92 días dejan pedir
    # un trimestre sin abrir la puerta a años enteros sin paginar.
    max_days = 92

    def extra_fields(self):
        return {
            "farm": serializers.UUIDField(required=False),
            "plot": serializers.UUIDField(required=False),
            "producer": serializers.UUIDField(required=False),
        }


# La lista responde un objeto con todo el periodo en `results`, no un arreglo: sin esto, el esquema
# supone que toda acción `list` responde un arreglo.
@extend_schema_serializer(many=False)
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
