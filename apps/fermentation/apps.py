from django.apps import AppConfig


class FermentationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fermentation"

    def ready(self):
        # La fermentación de cada lote, en la representación del lote. La precarga va desde el
        # lote.
        from apps.common.contracts.lot_details import register_lot_details

        from .serializers import LotFermentationSerializer

        register_lot_details(
            fields={
                "fermentation": lambda: LotFermentationSerializer(allow_null=True, read_only=True)
            },
            prefetch=["fermentation__facility"],
        )

        # Los volteos pendientes, en la evaluación de cada hora.
        from apps.common.contracts.alerts import register_evaluator

        from .alerts import evaluate

        register_evaluator("fermentation", evaluate)
