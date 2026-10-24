from django.apps import AppConfig


class DryingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.drying"

    def ready(self):
        # El secado de cada lote, en la representación del lote. La precarga va desde el lote.
        from apps.common.contracts.lot_details import register_lot_details

        from .lot_detail import LotDryingSerializer

        register_lot_details(
            fields={"drying": lambda: LotDryingSerializer(allow_null=True, read_only=True)},
            prefetch=["drying"],
        )
