from django.contrib import admin

from apps.common.admin import ReadOnlyAdminMixin

from .models import AgriculturalActivityAuditEvent


@admin.register(AgriculturalActivityAuditEvent)
class AgriculturalActivityAuditEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de las actividades con el valor anterior y el nuevo de cada cambio, de solo
    lectura."""

    list_display = ("activity_ref", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    readonly_fields = (
        "activity",
        "activity_ref",
        "plot_ref",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
