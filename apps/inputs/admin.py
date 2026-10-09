from django.contrib import admin

from apps.common.admin import ReadOnlyAdminMixin

from .models import AgriculturalInputAuditEvent


@admin.register(AgriculturalInputAuditEvent)
class AgriculturalInputAuditEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de cambios de los insumos con el valor anterior y nuevo de cada campo, de
    solo lectura."""

    list_display = ("input_name", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    readonly_fields = (
        "input_ref",
        "input_name",
        "version",
        "action",
        "actor",
        "changed_fields",
        "changes",
        "occurred_at",
    )
    search_fields = ("input_name",)

    # Solo superusuarios: el admin no filtra por productor, así que con el permiso de la API un
    # empleado de un productor vería los cambios de los insumos de todos.
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
