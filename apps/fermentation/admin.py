from django.contrib import admin

from apps.common.admin import ReadOnlyInlineMixin, SuperuserReadOnlyAdminMixin

from .models import FermentationProcess, FermentationProcessAuditEvent, FermentationTurn


class FermentationTurnInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = FermentationTurn
    fields = ("turned_at", "temperature_c", "ph", "notes", "recorded_by")
    readonly_fields = fields


@admin.register(FermentationProcess)
class FermentationProcessAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Las fermentaciones con sus volteos, de solo lectura: iniciar, voltear y finalizar ocupan y
    liberan el cajón y cambian el estado del lote, y eso solo lo hace la aplicación."""

    list_display = ("lot", "facility", "started_at", "ended_at", "responsible")
    list_select_related = ("lot", "facility", "responsible")
    search_fields = ("lot__code",)
    inlines = [FermentationTurnInline]


@admin.register(FermentationProcessAuditEvent)
class FermentationProcessAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de las fermentaciones y sus volteos, con el valor anterior y el nuevo de cada
    cambio, de solo lectura."""

    list_display = ("process", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("process__lot", "actor")
    readonly_fields = (
        "process",
        "turn_ref",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
