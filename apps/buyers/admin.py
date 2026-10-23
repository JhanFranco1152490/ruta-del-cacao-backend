from django.contrib import admin

from apps.common.admin import SuperuserReadOnlyAdminMixin

from .models import Buyer, BuyerAuditEvent


@admin.register(Buyer)
class BuyerAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "producer", "document_type", "buyer_type", "is_active")
    list_filter = ("buyer_type", "is_active")
    list_select_related = ("producer",)
    search_fields = ("name__unaccent", "identity_document")


@admin.register(BuyerAuditEvent)
class BuyerAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "buyer_ref", "action", "actor", "version")
    list_filter = ("action",)
