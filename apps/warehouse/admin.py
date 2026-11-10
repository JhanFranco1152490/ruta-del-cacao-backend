from django.contrib import admin

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.ownership import owner_filter

from .models import (
    StockAuditEvent,
    StockBalance,
    StockEntry,
    StockExit,
    StockMove,
    Warehouse,
    WarehouseAuditEvent,
)
from .services.warehouses import CONTENT_FIELDS, delete_warehouse, update_warehouse


class WarehouseAdminForm(VersionedAdminForm):
    class Meta:
        model = Warehouse
        fields = CONTENT_FIELDS


@admin.register(Warehouse)
class WarehouseAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = WarehouseAdminForm
    list_display = ("name", "farm", "is_active")
    list_filter = ("is_active",)
    list_select_related = ("farm",)
    search_fields = ("name__unaccent", "farm__name__unaccent")
    readonly_fields = ("farm", "version", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("farm", *CONTENT_FIELDS, "expected_version")}),
        ("Registro", {"fields": ("version", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request).filter(**owner_filter(request.user, "farm__producer_id"))
        )

    # El alta elige una finca que alcanza quien registra y es de la aplicación. La finca no se
    # edita: una bodega está en su finca.
    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        saved = run_service(
            update_warehouse,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in CONTENT_FIELDS},
        )
        obj.version = saved.version
        obj.updated_at = saved.updated_at

    def delete_model(self, request, obj):
        run_service(delete_warehouse, request.user, obj.pk, obj.version)


# Todo lo demás es de solo lectura: ingresar, sacar y anular cambian el saldo del lote y su estado,
# y eso solo lo hace la aplicación.


@admin.register(StockEntry)
class StockEntryAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("lot", "warehouse", "location", "entry_date", "g1_kg", "g2_kg", "entered_by")
    list_select_related = ("lot", "warehouse", "entered_by")
    search_fields = ("lot__code",)


@admin.register(StockBalance)
class StockBalanceAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("lot", "grade", "quantity_kg", "warehouse", "location")
    list_filter = ("grade",)
    list_select_related = ("lot", "warehouse")
    search_fields = ("lot__code",)


@admin.register(StockExit)
class StockExitAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "lot",
        "grade",
        "quantity_kg",
        "exit_date",
        "reason",
        "created_by",
        "voided_at",
    )
    list_filter = ("reason", "grade")
    list_select_related = ("lot", "created_by")
    search_fields = ("lot__code",)


@admin.register(StockMove)
class StockMoveAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("lot", "from_warehouse", "to_warehouse", "moved_by", "moved_at")
    list_select_related = ("lot", "from_warehouse", "to_warehouse", "moved_by")
    search_fields = ("lot__code",)


@admin.register(StockAuditEvent)
class StockAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de bodega de cada lote, con el valor anterior y el nuevo de cada cambio."""

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


@admin.register(WarehouseAuditEvent)
class WarehouseAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "warehouse_name", "action", "actor", "version")
    list_filter = ("action",)
    search_fields = ("warehouse_name__unaccent",)
