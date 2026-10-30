from django.apps import AppConfig


class LotsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lots"

    def ready(self):
        # Cómo se nombra un lote en un aviso.
        from apps.common.contracts.lot_representation import register_lot_brief

        from .serializers import LotBriefSerializer, lot_brief_prefetch

        register_lot_brief(LotBriefSerializer, lot_brief_prefetch)
