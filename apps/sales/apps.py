from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sales"

    def ready(self):
        # Los kilos vendidos, para los paneles de indicadores.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import sales_by_farm

        register_indicator_source("sales", sales_by_farm)

        # Las líneas de venta una por una, para los reportes del productor.
        from apps.common.contracts.reports import register_report_source

        from .reports import sale_rows, sales_by_lot

        register_report_source("sale_rows", sale_rows)
        register_report_source("sales_by_lot", sales_by_lot)

        # Las ventas como etapas de la historia del lote, y lo vendido.
        from apps.common.contracts.lot_history import (
            register_lot_history_source,
            register_stage_serializer,
        )

        from .history import SaleStageSerializer, sales_history, sold_now

        register_lot_history_source("sales_history", sales_history)
        register_lot_history_source("sold_now", sold_now)
        register_stage_serializer("sale", SaleStageSerializer)

        # Su historial, en la bitácora de cambios.
        from apps.common.contracts.audit_log import register_audit_source

        from .audit_log import SOURCE

        register_audit_source("sale", SOURCE)
