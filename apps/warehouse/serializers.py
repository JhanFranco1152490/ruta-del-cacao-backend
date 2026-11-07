from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, full_name

from .choices import ExitReason, Grade
from .models import ONE_DECIMAL, StockEntry, Warehouse
from .rules import entry_is_intact
from .services.stock_queries import ORDERINGS

# Las opciones del estado del lote se toman de su campo por la relación, sin importar su app: así
# el esquema las reconoce como el mismo enum de los lotes.
LOT_STATUS_CHOICES = (
    StockEntry._meta.get_field("lot").related_model._meta.get_field("status").choices
)


def _decimal(max_digits, **kwargs):
    return serializers.DecimalField(max_digits=max_digits, decimal_places=ONE_DECIMAL, **kwargs)


class WarehouseFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class WarehouseSerializer(serializers.ModelSerializer):
    farm = WarehouseFarmSerializer(read_only=True)
    # Si la bodega alguna vez recibió un ingreso: lo deja el servicio, que lo calcula en la misma
    # consulta. Con eso la interfaz ofrece eliminar o solo desactivar.
    in_use = serializers.BooleanField(read_only=True)

    class Meta:
        model = Warehouse
        fields = ["id", "farm", "name", "is_active", "in_use", "version"]
        read_only_fields = fields


class WarehouseListQuerySerializer(serializers.Serializer):
    # `page` y `page_size` los lee la paginación.
    farm = serializers.UUIDField(required=False)
    active = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=40)
    producer = serializers.UUIDField(required=False)


class ExistingWarehouseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class WarehouseConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y `existing` con `warehouse_name_taken`.
    current = WarehouseSerializer(required=False)
    existing = ExistingWarehouseSerializer(required=False)


class StockPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, account) -> str:
        return full_name(account)


class StockLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LOT_STATUS_CHOICES)
    # La que piden ingresar en `expected_lot_version`.
    version = serializers.IntegerField()


class StockLotRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()


class StockFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class StockWarehouseRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class StockClassifiedSerializer(serializers.Serializer):
    g1_kg = _decimal(7)
    g2_kg = _decimal(7)
    classified_at = serializers.DateTimeField()


class StockEntrySerializer(serializers.Serializer):
    entry_date = serializers.DateField()
    warehouse = StockWarehouseRefSerializer()
    location = serializers.CharField()
    g1_kg = _decimal(7)
    g2_kg = _decimal(7)
    entered_at = serializers.DateTimeField()
    entered_by = StockPersonSerializer()
    corrected_at = serializers.DateTimeField(allow_null=True)
    corrected_by = StockPersonSerializer(allow_null=True)
    # Si el estado lo permite: nada ha salido del lote. El permiso lo decide quien llama.
    can_correct = serializers.SerializerMethodField()
    version = serializers.IntegerField()

    def get_can_correct(self, entry: StockEntry) -> bool:
        lot = entry.lot
        balances = {balance.grade: balance.quantity_kg for balance in lot.stock_balances.all()}
        entered = {Grade.G1: entry.g1_kg, Grade.G2: entry.g2_kg}
        return lot.status == "in_warehouse" and entry_is_intact(entered, balances)


class StockBalanceSerializer(serializers.Serializer):
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = _decimal(7)


class StockVoidSerializer(serializers.Serializer):
    voided_at = serializers.DateTimeField()
    voided_by = StockPersonSerializer()
    reason = serializers.CharField(source="void_reason")


class StockExitSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = _decimal(7)
    exit_date = serializers.DateField()
    reason = serializers.ChoiceField(choices=ExitReason.choices)
    detail = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_by = StockPersonSerializer()
    voided = serializers.SerializerMethodField()
    can_void = serializers.SerializerMethodField()

    def get_voided(self, stock_exit) -> dict | None:
        if stock_exit.voided_at is None:
            return None
        return StockVoidSerializer(stock_exit).data

    def get_can_void(self, stock_exit) -> bool:
        return stock_exit.voided_at is None and stock_exit.reason != ExitReason.SALE


# Un lote Clasificado o En bodega, con su ingreso, sus existencias por calibre y el historial de
# sus salidas.
class LotStockSerializer(serializers.Serializer):
    lot = StockLotSerializer(source="*")
    farm = StockFarmSerializer(source="harvest.plot.farm")
    classified = StockClassifiedSerializer(source="classification")
    entry = StockEntrySerializer(source="stock_entry", allow_null=True)
    balances = StockBalanceSerializer(source="stock_balances", many=True)
    exits = StockExitSerializer(source="stock_exits", many=True)


class PendingEntrySerializer(serializers.Serializer):
    lot = StockLotRefSerializer(source="*")
    farm = StockFarmSerializer(source="harvest.plot.farm")
    g1_kg = _decimal(7, source="classification.g1_kg")
    g2_kg = _decimal(7, source="classification.g2_kg")
    classified_at = serializers.DateTimeField(source="classification.classified_at")


class PendingEntryQuerySerializer(serializers.Serializer):
    # `page` y `page_size` los lee la paginación.
    farm = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=40)
    producer = serializers.UUIDField(required=False)


class StockConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 409 lo arma el manejador global de errores. `current` llega con
    # `stale_version` y `current_status` con `lot_invalid_status`.
    current = LotStockSerializer(required=False)
    current_status = serializers.CharField(required=False)


class StockInsufficientErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: `available_kg` llega con `stock_insufficient`.
    available_kg = serializers.CharField(required=False)


class StockRowSerializer(serializers.Serializer):
    lot = StockLotRefSerializer()
    farm = StockFarmSerializer(source="lot.harvest.plot.farm")
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = _decimal(7)
    warehouse = StockWarehouseRefSerializer()
    location = serializers.CharField()
    entry_date = serializers.DateField(source="lot.stock_entry.entry_date")


class StockSummaryQuerySerializer(serializers.Serializer):
    # Los filtros de la pantalla; `page` y `page_size` los lee la paginación.
    farm = serializers.UUIDField(required=False)
    warehouse = serializers.UUIDField(required=False)
    grade = serializers.ChoiceField(choices=Grade.choices, required=False)
    location = serializers.CharField(required=False, allow_blank=True, max_length=60)
    search = serializers.CharField(required=False, allow_blank=True, max_length=40)
    producer = serializers.UUIDField(required=False)


class StockListQuerySerializer(StockSummaryQuerySerializer):
    ordering = serializers.ChoiceField(
        choices=[*ORDERINGS, *(f"-{key}" for key in ORDERINGS)], required=False
    )


class StockSummarySerializer(serializers.Serializer):
    g1_kg = serializers.DecimalField(max_digits=12, decimal_places=ONE_DECIMAL)
    g2_kg = serializers.DecimalField(max_digits=12, decimal_places=ONE_DECIMAL)
    lots = serializers.IntegerField()


class StockLocationsQuerySerializer(serializers.Serializer):
    warehouse = serializers.UUIDField()


class StockLocationsSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.CharField())
