from django.contrib import admin

from apps.common.admin import SuperuserReadOnlyAdminMixin

from .models import Harvest, HarvestAuditEvent


@admin.register(Harvest)
class HarvestAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Las cosechas, de solo lectura: corregir y eliminar tienen reglas (el lote que forman, la
    versión) que solo aplica la aplicación, y el admin no filtra por productor."""

    list_display = ("harvest_date", "plot", "variety", "green_weight_kg", "collector")
    list_filter = ("harvest_date",)
    list_select_related = ("plot__farm", "variety", "collector")
    search_fields = ("plot__name__unaccent", "plot__farm__name__unaccent")


@admin.register(HarvestAuditEvent)
class HarvestAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de las cosechas con el valor anterior y el nuevo de cada cambio, de solo
    lectura."""

    list_display = ("harvest_ref", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    readonly_fields = (
        "harvest",
        "harvest_ref",
        "plot_ref",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
