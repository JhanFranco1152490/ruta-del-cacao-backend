from django.apps import AppConfig


class ProducersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.producers"

    def ready(self):
        # Reactivar la cuenta Productor reactiva también al productor; la app de cuentas lo pide
        # por el registro común, sin importar esta.
        from apps.common.contracts.producer_reactivation import register_producer_reactivator

        from .services import reactivate_with_account

        register_producer_reactivator(reactivate_with_account)
