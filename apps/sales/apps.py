from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sales"

    def ready(self):
        # Los kilos vendidos, para los paneles de indicadores.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import sales_by_farm

        register_indicator_source("sales", sales_by_farm)
