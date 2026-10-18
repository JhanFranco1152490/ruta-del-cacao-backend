from django.contrib import admin

from apps.common.admin import ReadOnlyInlineMixin, SuperuserReadOnlyAdminMixin

from .models import AgriculturalActivity, AgriculturalActivityAuditEvent, AgriculturalActivityInput


class ActivityInputInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = AgriculturalActivityInput
    fields = ("input", "quantity", "stock_movement")
    readonly_fields = fields


@admin.register(AgriculturalActivity)
class AgriculturalActivityAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Las actividades con los insumos que gastaron, de solo lectura: una realización no se
    modifica y el resto tiene reglas de fecha y de estado que solo aplica la aplicación."""

    list_display = ("activity_type", "plot", "scheduled_date", "status", "assignee")
    list_filter = ("status", "activity_type")
    list_select_related = ("plot__farm", "assignee")
    search_fields = ("plot__name__unaccent", "plot__farm__name__unaccent")
    inlines = [ActivityInputInline]


@admin.register(AgriculturalActivityAuditEvent)
class AgriculturalActivityAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
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
