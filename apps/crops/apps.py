from django.apps import AppConfig


class CropsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crops"

    def ready(self):
        from apps.common.plot_characterization import register_characterized

        from .plot_characterization import plot_is_characterized

        register_characterized(plot_is_characterized)
