from django.apps import AppConfig


class PostharvestParametersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.postharvest_parameters"

    def ready(self):
        # Cómo leen las demás apps los parámetros vigentes de un productor.
        from apps.common.contracts.postharvest_parameters import register_drying_parameters

        from .services.read import current_parameters

        register_drying_parameters(current_parameters)
