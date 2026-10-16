from django.contrib import admin

from apps.common.admin import SuperuserReadOnlyAdminMixin

from .models import Lot, LotAuditEvent, LotCodeSequence


@admin.register(Lot)
class LotAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Los lotes, de solo lectura: el código es inmutable y el estado solo cambia por la cadena de
    estados de la aplicación, que registra cada paso."""

    list_display = ("code", "status", "harvest", "created_by", "created_at")
    list_filter = ("status",)
    list_select_related = ("harvest__plot__farm", "created_by")
    search_fields = ("code",)
    readonly_fields = (
        "code",
        "status",
        "harvest",
        "created_by",
        "version",
        "created_at",
        "updated_at",
    )


@admin.register(LotCodeSequence)
class LotCodeSequenceAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El último consecutivo de lote de cada parcela y día, de solo lectura: no baja nunca."""

    list_display = ("plot", "harvest_date", "last_value")
    list_select_related = ("plot__farm",)


@admin.register(LotAuditEvent)
class LotAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de los lotes con su código, de solo lectura; sobrevive al lote eliminado."""

    list_display = ("code", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    search_fields = ("code",)
    readonly_fields = (
        "lot",
        "lot_ref",
        "code",
        "harvest_ref",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
