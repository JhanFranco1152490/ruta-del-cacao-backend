from django.apps import AppConfig


class LotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lots"

    def ready(self):
        # Cómo se nombra un lote en un aviso.
        from apps.common.contracts.lot_representation import register_lot_brief

        from .serializers import LotBriefSerializer, lot_brief_prefetch

        register_lot_brief(LotBriefSerializer, lot_brief_prefetch)

        # Que el lote de un filtro de reportes exista y esté en el alcance.
        from apps.common.contracts.reports import register_report_source

        from .reports import lot_in_scope, lot_rows

        register_report_source("lot_in_scope", lot_in_scope)
        # Los lotes uno por uno, para el reporte de trazabilidad.
        register_report_source("lot_rows", lot_rows)
