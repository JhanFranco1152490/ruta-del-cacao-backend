from django.contrib import admin

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.ownership import owner_filter

from .models import Buyer, BuyerAuditEvent
from .services.create import CONTENT_FIELDS
from .services.delete import delete_buyer
from .services.update import update_buyer
from .usage import used_expression


class BuyerAdminForm(VersionedAdminForm):
    class Meta:
        model = Buyer
        fields = CONTENT_FIELDS


@admin.register(Buyer)
class BuyerAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = BuyerAdminForm
    list_display = ("name", "producer", "buyer_type", "is_active", "has_records")
    list_filter = ("buyer_type", "is_active")
    list_select_related = ("producer",)
    search_fields = (
        "name__unaccent",
        "identity_document",
        "producer__member_code",
        "producer__first_name__unaccent",
        "producer__last_name__unaccent",
    )
    readonly_fields = ("producer", "version", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("producer", *CONTENT_FIELDS, "expected_version")}),
        ("Registro", {"fields": ("version", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(**owner_filter(request.user))
            .annotate(has_records=used_expression())
        )

    @admin.display(boolean=True, description="Con ventas")
    def has_records(self, obj):
        return obj.has_records

    # El alta lleva el productor dueño y es de la aplicación.
    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        saved = run_service(
            update_buyer,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in CONTENT_FIELDS},
        )
        obj.version = saved.version
        obj.updated_at = saved.updated_at

    def delete_model(self, request, obj):
        run_service(delete_buyer, request.user, obj.pk, obj.version)


@admin.register(BuyerAuditEvent)
class BuyerAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de cambios de los compradores, de solo lectura: qué campos cambiaron, sin sus
    valores."""

    list_display = ("occurred_at", "buyer_ref", "buyer_type", "action", "actor", "version")
    list_filter = ("action",)
    list_select_related = ("actor",)
    readonly_fields = (
        "buyer_ref",
        "buyer_type",
        "version",
        "action",
        "actor",
        "changed_fields",
        "occurred_at",
    )
