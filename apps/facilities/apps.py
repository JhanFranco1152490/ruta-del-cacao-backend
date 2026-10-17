from django.apps import AppConfig


class FacilitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.facilities"

    def ready(self):
        # Lo que esta app elimina cuando se elimina una finca creada por error.
        from apps.common.farm_dependents import register_dependent

        from .farm_dependent import facilities_dependent

        register_dependent(facilities_dependent)
