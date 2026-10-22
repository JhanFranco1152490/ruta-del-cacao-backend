from django.apps import AppConfig


class InputsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inputs"

    def ready(self):
        from apps.common.contracts.farm_dependents import (
            register_dependent as register_farm_dependent,
        )
        from apps.common.contracts.producer_dependents import register_dependent

        from .farm_dependent import inputs_dependent as inputs_of_a_farm
        from .producer_dependent import inputs_dependent

        register_dependent(inputs_dependent)
        register_farm_dependent(inputs_of_a_farm)
