from django.contrib import admin

from apps.common.admin import SuperuserReadOnlyAdminMixin

from .models import LotClassification, LotDiscard, QualityAuditEvent, QualityEvaluation

# Todo de solo lectura: evaluar, clasificar y descartar cambian el estado del lote, y el descarte
# avisa al equipo de la finca; eso solo lo hace la aplicación.


@admin.register(QualityEvaluation)
class QualityEvaluationAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "lot",
        "well_fermented_pct",
        "moldy_pct",
        "other_defects_pct",
        "evaluated_by",
        "evaluated_at",
        "corrected_at",
    )
    list_select_related = ("lot", "evaluated_by")
    search_fields = ("lot__code",)


@admin.register(LotClassification)
class LotClassificationAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "lot",
        "g1_kg",
        "g2_kg",
        "discard_kg",
        "discard_reason",
        "classified_by",
        "classified_at",
    )
    list_filter = ("discard_reason",)
    list_select_related = ("lot", "classified_by")
    search_fields = ("lot__code",)


@admin.register(LotDiscard)
class LotDiscardAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("lot", "reason", "discarded_by", "discarded_at")
    list_filter = ("reason",)
    list_select_related = ("lot", "discarded_by")
    search_fields = ("lot__code",)


@admin.register(QualityAuditEvent)
class QualityAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de calidad de cada lote, con el valor anterior y el nuevo de cada cambio."""

    list_display = ("lot", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("lot", "actor")
    search_fields = ("lot__code",)
    readonly_fields = (
        "lot",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
