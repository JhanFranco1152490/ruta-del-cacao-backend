from django.contrib import admin

from apps.common.admin import SuperuserReadOnlyAdminMixin

from .fields import FIELDS
from .models import PostharvestParameters, PostharvestParametersAuditEvent


@admin.register(PostharvestParameters)
class PostharvestParametersAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("producer", "updated_at", "version")
    list_select_related = ("producer",)
    fields = ("producer", *FIELDS, "updated_by", "version", "created_at", "updated_at")


@admin.register(PostharvestParametersAuditEvent)
class PostharvestParametersAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "producer", "action", "actor", "version")
    list_filter = ("action",)
    list_select_related = ("producer", "actor")
