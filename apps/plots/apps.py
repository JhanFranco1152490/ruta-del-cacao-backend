from django.apps import AppConfig


class PlotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plots"

    def ready(self):
        from apps.common.farm_dependents import register_dependent

        from .farm_dependent import plots_dependent

        register_dependent(plots_dependent)
