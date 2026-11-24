from django.apps import AppConfig


class CropsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crops"

    def ready(self):
        from apps.common.contracts.plot_characterization import register_characterized
        from apps.common.contracts.plot_trees import register_tree_count

        from .plot_characterization import plot_is_characterized, plot_tree_count

        register_characterized(plot_is_characterized)
        register_tree_count(plot_tree_count)

        # Su historial, en la bitácora de cambios.
        from apps.common.contracts.audit_log import register_audit_source

        from .audit_log import SOURCE

        register_audit_source("plot_characterization", SOURCE)
