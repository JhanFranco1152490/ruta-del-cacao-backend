from django.apps import AppConfig


class ActivitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.activities"

    def ready(self):
        # Lo que esta app elimina cuando se elimina una parcela creada por error.
        from apps.common.farm_change_guards import register_guard
        from apps.common.plot_dependents import register_dependent

        from .farm_change_guard import pending_activities
        from .plot_dependent import activities_dependent

        register_dependent(activities_dependent)
        # Lo que impide cambiar de finca a quien tiene labores por hacer en ella.
        register_guard("activities", pending_activities)
