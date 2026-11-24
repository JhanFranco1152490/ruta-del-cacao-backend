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

        # Las existencias de hoy una por una, para los reportes del productor.
        from apps.common.contracts.reports import register_report_source

        from .reports import stock_by_lot, stock_rows

        register_report_source("stock_by_lot", stock_by_lot)
        register_report_source("stock_rows", stock_rows)

        # El ingreso, los cambios de lugar y las salidas como etapas de la historia del lote, y lo
        # que le queda hoy.
        from apps.common.contracts.lot_history import (
            register_lot_history_source,
            register_stage_serializer,
        )

        from .history import (
            StockEntryStageSerializer,
            StockExitStageSerializer,
            StockMoveStageSerializer,
            stock_now,
            warehouse_history,
        )

        register_lot_history_source("warehouse_history", warehouse_history)
        register_lot_history_source("stock_now", stock_now)
        register_stage_serializer("stock_entry", StockEntryStageSerializer)
        register_stage_serializer("stock_move", StockMoveStageSerializer)
        register_stage_serializer("stock_exit", StockExitStageSerializer)

        # Su historial, en la bitácora de cambios.
        from apps.common.contracts.audit_log import register_audit_source

        from .audit_log import STOCK_SOURCE, WAREHOUSE_SOURCE

        register_audit_source("stock", STOCK_SOURCE)
        register_audit_source("warehouse", WAREHOUSE_SOURCE)
