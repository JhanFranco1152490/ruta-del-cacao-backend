from django.apps import AppConfig


class FarmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.farms"

    def ready(self):
        from apps.common.contracts.producer_dependents import register_dependent

        from .producer_dependent import farms_dependent

        register_dependent(farms_dependent)

        # Qué fincas entran a los paneles de indicadores y cómo se nombran.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import farm_scope, scoped_farms

        register_indicator_source("farm_scope", farm_scope)
        register_indicator_source("farms", scoped_farms)
