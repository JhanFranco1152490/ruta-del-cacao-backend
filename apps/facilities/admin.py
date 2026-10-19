from django.contrib import admin

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.ownership import owner_filter

from .models import PostharvestFacility, PostharvestFacilityAuditEvent
from .services.create import CONTENT_FIELDS
from .services.delete import delete_facility
from .services.update import update_facility


class PostharvestFacilityAdminForm(VersionedAdminForm):
    class Meta:
        model = PostharvestFacility
        fields = CONTENT_FIELDS


@admin.register(PostharvestFacility)
class PostharvestFacilityAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = PostharvestFacilityAdminForm
    list_display = ("name", "farm", "facility_type", "capacity_kg", "is_active")
    list_filter = ("facility_type", "is_active")
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
    # edita: un elemento está construido en una.
    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        saved = run_service(
            update_facility,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in CONTENT_FIELDS},
        )
        obj.version = saved.version
        obj.updated_at = saved.updated_at

    def delete_model(self, request, obj):
        run_service(delete_facility, request.user, obj.pk, obj.version)


@admin.register(PostharvestFacilityAuditEvent)
class PostharvestFacilityAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "facility_name", "action", "actor", "version")
    list_filter = ("action",)
    search_fields = ("facility_name__unaccent",)
