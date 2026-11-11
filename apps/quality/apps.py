from django.apps import AppConfig


class QualityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.quality"

    def ready(self):
        # La calidad de cada lote, en la representación del lote. La precarga va desde el lote.
        from apps.common.contracts.lot_details import register_lot_details

        from .lot_detail import LotQualityDetailSerializer

        register_lot_details(
            fields={
                "quality": lambda: LotQualityDetailSerializer(
                    source="*", allow_null=True, read_only=True
                )
            },
            prefetch=["quality_evaluation", "classification", "discard"],
        )

        # Lo clasificado y lo descartado, para los paneles de indicadores.
        from apps.common.contracts.indicators import register_indicator_source

        from .indicators import quality_by_farm

        register_indicator_source("quality", quality_by_farm)
