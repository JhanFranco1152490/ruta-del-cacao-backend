from django.contrib import admin

from apps.common.admin import ReadOnlyAdminMixin, SuperuserReadOnlyAdminMixin
from apps.common.ownership import owner_filter

from .models import PostharvestFacility, PostharvestFacilityAuditEvent


@admin.register(PostharvestFacility)
class PostharvestFacilityAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    # De solo lectura mientras no existan los servicios de edición y borrado: escribir directo en
    # el modelo saltaría la regla del nombre repetido y el historial.
    list_display = ("name", "farm", "facility_type", "capacity_kg", "is_active")
    list_filter = ("facility_type", "is_active")
    list_select_related = ("farm",)
    search_fields = ("name__unaccent", "farm__name__unaccent")

    def get_queryset(self, request):
        return (
            super().get_queryset(request).filter(**owner_filter(request.user, "farm__producer_id"))
        )


@admin.register(PostharvestFacilityAuditEvent)
class PostharvestFacilityAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "facility_name", "action", "actor", "version")
    list_filter = ("action",)
    search_fields = ("facility_name__unaccent",)
