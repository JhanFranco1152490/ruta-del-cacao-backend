from django.apps import AppConfig


class InputsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inputs"

    def ready(self):
        from apps.common.producer_dependents import register_dependent

        from .producer_dependent import inputs_dependent

        register_dependent(inputs_dependent)
