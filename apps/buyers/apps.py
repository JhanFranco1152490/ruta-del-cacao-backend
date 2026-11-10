from django.apps import AppConfig


class BuyersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.buyers"

    def ready(self):
        # Lo que esta app elimina cuando se elimina un productor creado por error.
        from apps.common.contracts.producer_dependents import register_dependent

        from .producer_dependent import buyers_dependent

        register_dependent(buyers_dependent)
