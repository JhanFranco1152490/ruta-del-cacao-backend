from django.apps import AppConfig


class HarvestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.harvests"

    def ready(self):
        # Una parcela con cosechas no se elimina: se desactiva.
        from apps.common.contracts.plot_dependents import register_dependent

        from .plot_dependent import harvests_dependent

        register_dependent(harvests_dependent)

        # Los kg en baba de los paneles de indicadores.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import harvested

        register_indicator_source("harvests", harvested)
