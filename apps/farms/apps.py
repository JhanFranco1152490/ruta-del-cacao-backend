from django.apps import AppConfig


class FarmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.farms"

    def ready(self):
        from apps.common.producer_dependents import register_dependent

        from .producer_dependent import farms_dependent

        register_dependent(farms_dependent)
