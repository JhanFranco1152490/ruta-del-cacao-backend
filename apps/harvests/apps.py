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

        from .indicators import harvested, harvested_by_variety

        register_indicator_source("harvests", harvested)
        register_indicator_source("harvest_varieties", harvested_by_variety)

        # Las cosechas una por una, para los reportes del productor.
        from apps.common.contracts.reports import register_report_source

        from .reports import harvest_rows

        register_report_source("harvest_rows", harvest_rows)

        # Su historial, en la bitácora de cambios.
        from apps.common.contracts.audit_log import register_audit_source

        from .audit_log import SOURCE

        register_audit_source("harvest", SOURCE)
