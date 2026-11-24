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

        # Las fechas de la fermentación de cada lote, para el reporte de trazabilidad.
        from apps.common.contracts.reports import register_report_source

        from .reports import fermentation_dates

        register_report_source("fermentation_dates", fermentation_dates)

        # La fermentación como etapa de la historia del lote, con sus volteos.
        from apps.common.contracts.lot_history import (
            register_lot_history_source,
            register_stage_serializer,
        )

        from .history import FermentationStageSerializer, fermentation_history

        register_lot_history_source("fermentation_history", fermentation_history)
        register_stage_serializer("fermentation", FermentationStageSerializer)

        # Su historial, en la bitácora de cambios.
        from apps.common.contracts.audit_log import register_audit_source

        from .audit_log import SOURCE

        register_audit_source("fermentation", SOURCE)
