from django.apps import AppConfig


class PlotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plots"

    def ready(self):
        from apps.common.contracts.farm_dependents import register_dependent

        from .farm_dependent import plots_dependent

        register_dependent(plots_dependent)

        # El área declarada de cada parcela, para los kg por hectárea de los paneles.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import plot_areas

        register_indicator_source("plots", plot_areas)

        # Que la parcela de un filtro de reportes exista y esté en el alcance.
        from apps.common.contracts.reports import register_report_source

        from .reports import plot_in_scope

        register_report_source("plot_in_scope", plot_in_scope)
