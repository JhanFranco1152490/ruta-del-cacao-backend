from decimal import Decimal
from types import SimpleNamespace

from rest_framework import serializers

from .models import ONE_DECIMAL


def _decimal(**kwargs):
    return serializers.DecimalField(max_digits=7, decimal_places=ONE_DECIMAL, **kwargs)


# Lo que bodega agrega a la representación de un lote: dónde quedó y cuánto hay de cada calibre.
# Nulo mientras el lote no haya ingresado.
class LotWarehouseDetailSerializer(serializers.Serializer):
    entry_date = serializers.DateField()
    warehouse_name = serializers.CharField()
    location = serializers.CharField()
    g1_entered_kg = _decimal()
    g2_entered_kg = _decimal()
    g1_available_kg = _decimal()
    g2_available_kg = _decimal()

    def to_representation(self, lot):
        entry = getattr(lot, "stock_entry", None)
        if entry is None:
            return None
        # Un calibre ingresado en 0 no tiene fila de existencias; uno agotado la tiene en 0.
        available = {balance.grade: balance.quantity_kg for balance in lot.stock_balances.all()}
        return super().to_representation(
            SimpleNamespace(
                entry_date=entry.entry_date,
                warehouse_name=entry.warehouse.name,
                location=entry.location,
                g1_entered_kg=entry.g1_kg,
                g2_entered_kg=entry.g2_kg,
                g1_available_kg=available.get("g1", Decimal("0.0")),
                g2_available_kg=available.get("g2", Decimal("0.0")),
            )
        )
