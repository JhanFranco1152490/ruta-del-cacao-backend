from django.apps import AppConfig


class WarehouseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.warehouse"

    def ready(self):
        # Lo que esta app elimina cuando se elimina una finca creada por error.
        from apps.common.contracts.farm_dependents import register_dependent

        from .farm_dependent import warehouses_dependent

        register_dependent(warehouses_dependent)

        # Dónde quedó el lote y cuánto hay de cada calibre, en la representación del lote. La
        # precarga va desde el lote.
        from apps.common.contracts.lot_details import register_lot_details

        from .lot_detail import LotWarehouseDetailSerializer

        register_lot_details(
            fields={
                "warehouse": lambda: LotWarehouseDetailSerializer(
                    source="*", allow_null=True, read_only=True
                )
            },
            prefetch=["stock_entry__warehouse", "stock_balances"],
        )

        # Las existencias de hoy, para el panel del productor.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import stock_by_farm

        register_indicator_source("warehouse", stock_by_farm)
