from rest_framework import serializers

from .models import ONE_DECIMAL


class LotDryingSerializer(serializers.Serializer):
    # Lo que el secado agrega a la representación de un lote: el peso seco es el que sigue en
    # calidad y bodega, y el rendimiento el que muestran sus tarjetas.
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    facility = serializers.CharField(source="facility.name")
    final_moisture_pct = serializers.DecimalField(
        max_digits=4, decimal_places=ONE_DECIMAL, allow_null=True
    )
    dry_weight_kg = serializers.DecimalField(
        max_digits=7, decimal_places=ONE_DECIMAL, allow_null=True
    )
    yield_pct = serializers.DecimalField(max_digits=4, decimal_places=ONE_DECIMAL, allow_null=True)
