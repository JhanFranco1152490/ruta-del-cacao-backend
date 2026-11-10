from django.contrib import admin

from apps.common.admin import ReadOnlyInlineMixin, SuperuserReadOnlyAdminMixin

from .models import Sale, SaleAuditEvent, SaleCodeSequence, SaleLine


class SaleLineInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = SaleLine
    fields = ("lot", "grade", "quantity_kg", "price_per_kg", "subtotal", "stock_exit")
    readonly_fields = fields


@admin.register(Sale)
class SaleAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Las ventas, de solo lectura: registrar, anular y el soporte descuentan o devuelven
    existencias de bodega, y se hacen desde la aplicación."""

    list_display = ("__str__", "sale_date", "farm", "buyer", "voided_at")
    list_filter = ("sale_date",)
    list_select_related = ("farm", "buyer")
    search_fields = ("buyer__name__unaccent", "farm__name__unaccent")
    inlines = [SaleLineInline]


@admin.register(SaleCodeSequence)
class SaleCodeSequenceAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El último número de venta de cada productor, de solo lectura: no baja nunca."""

    list_display = ("producer", "last_value")
    list_select_related = ("producer",)


@admin.register(SaleAuditEvent)
class SaleAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "sale", "action", "actor", "version")
    list_filter = ("action",)
    list_select_related = ("sale", "actor")
