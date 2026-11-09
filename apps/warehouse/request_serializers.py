"""Lo que reciben las escrituras de bodega."""

from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin, RequireVersionedChangeMixin

from .choices import MANUAL_EXIT_REASONS, ExitReason, Grade
from .models import DETAIL_MAX_LENGTH, LOCATION_MAX_LENGTH, NAME_MAX_LENGTH, ONE_DECIMAL


class WarehouseCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    farm_id = serializers.UUIDField()
    # Un nombre que solo tiene guiones lo rechaza el modelo (`clean`), que lo normaliza.
    name = serializers.CharField(max_length=NAME_MAX_LENGTH)


class WarehouseUpdateSerializer(
    RequireVersionedChangeMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    # Sin `farm_id`: una bodega está en su finca y no se muda. Si llega, el mixin lo rechaza.
    name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False)
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)


class WarehouseDeleteSerializer(serializers.Serializer):
    # Query param del DELETE, con la versión leída: no se elimina una bodega que otra persona
    # acaba de cambiar.
    expected_version = serializers.IntegerField(min_value=1)


WAREHOUSE_REQUIRED = "Elija la bodega"


def _required_message(message: str) -> dict:
    return {"required": message, "blank": message, "null": message, "invalid": message}


class EntryCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # La versión del lote que se leyó: si otra persona lo cambió, no se ingresa a ciegas. Los kilos
    # no viajan: son los de la clasificación, que no cambia.
    expected_lot_version = serializers.IntegerField(min_value=1)
    entry_date = serializers.DateField()
    warehouse_id = serializers.UUIDField(error_messages=_required_message(WAREHOUSE_REQUIRED))
    # Opcional: sin ella el ingreso queda sin ubicación dentro de la bodega.
    location = serializers.CharField(
        max_length=LOCATION_MAX_LENGTH, required=False, allow_blank=True, default=""
    )


class EntryUpdateSerializer(
    RequireVersionedChangeMixin, RejectUnknownFieldsMixin, serializers.Serializer
):
    # Los kilos no se corrigen: son los de la clasificación.
    entry_date = serializers.DateField(required=False)
    warehouse_id = serializers.UUIDField(
        required=False, error_messages=_required_message(WAREHOUSE_REQUIRED)
    )
    # Vacía quita la ubicación.
    location = serializers.CharField(
        max_length=LOCATION_MAX_LENGTH, required=False, allow_blank=True
    )
    # La versión del ingreso que se leyó.
    expected_version = serializers.IntegerField(min_value=1)


EXIT_REASON_CHOICES = [(value, ExitReason(value).label) for value in MANUAL_EXIT_REASONS]


class ExitCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Una salida es de un solo calibre. Venta no se puede elegir: la genera la venta.
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = serializers.DecimalField(
        max_digits=8,
        decimal_places=ONE_DECIMAL,
        min_value=Decimal("0.1"),
        error_messages={"min_value": "La cantidad debe ser mayor que 0"},
    )
    exit_date = serializers.DateField()
    reason = serializers.ChoiceField(choices=EXIT_REASON_CHOICES)
    detail = serializers.CharField(
        max_length=DETAIL_MAX_LENGTH, allow_blank=True, required=False, default=""
    )


class ExitVoidSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(
        max_length=DETAIL_MAX_LENGTH,
        error_messages=_required_message("Indique el motivo de la anulación"),
    )
