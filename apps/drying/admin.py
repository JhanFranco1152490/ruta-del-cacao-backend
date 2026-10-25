from django.contrib import admin

from apps.common.admin import ReadOnlyInlineMixin, SuperuserReadOnlyAdminMixin

from .models import DryingLogEntry, DryingProcess, DryingProcessAuditEvent


class DryingLogEntryInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = DryingLogEntry
    fields = (
        "day_number",
        "measured_at",
        "moisture_pct",
        "sun_hours",
        "shade_hours",
        "turn_count",
        "turn_frequency_hours",
        "weather",
        "notes",
        "recorded_by",
    )
    readonly_fields = fields


@admin.register(DryingProcess)
class DryingProcessAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Los secados con su bitácora, de solo lectura: iniciar, registrar y finalizar ocupan y
    liberan la marquesina y cambian el estado del lote, y eso solo lo hace la aplicación."""

    list_display = ("lot", "facility", "started_at", "ended_at", "yield_pct", "responsible")
    list_select_related = ("lot", "facility", "responsible")
    search_fields = ("lot__code",)
    inlines = [DryingLogEntryInline]


@admin.register(DryingProcessAuditEvent)
class DryingProcessAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de los secados y su bitácora, con el valor anterior y el nuevo de cada cambio,
    de solo lectura."""

    list_display = ("process", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("process__lot", "actor")
    readonly_fields = (
        "process",
        "log_ref",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
