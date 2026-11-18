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
