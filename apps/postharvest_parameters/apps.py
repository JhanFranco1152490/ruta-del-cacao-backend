from django.apps import AppConfig


class PostharvestParametersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.postharvest_parameters"

    def ready(self):
        from apps.common.contracts.postharvest_parameters import register_drying_parameters
        from apps.common.contracts.producer_dependents import register_dependent

        from .producer_dependent import parameters_dependent
        from .services.read import current_parameters

        # Cómo leen las demás apps los parámetros vigentes de un productor.
        register_drying_parameters(current_parameters)
        # Lo que esta app elimina cuando se elimina un productor creado por error.
        register_dependent(parameters_dependent)
