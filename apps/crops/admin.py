from django import forms
from django.contrib import admin

from .exceptions import DuplicateVarietyName
from .models import CacaoVariety, PlotCharacterizationAuditEvent
from .services import create_variety, delete_variety, name_taken, update_variety

EDITABLE_FIELDS = ("name", "description", "is_active")
MANAGE_PERMISSION = "crops.manage_cacaovariety"


class CacaoVarietyAdminForm(forms.ModelForm):
    class Meta:
        model = CacaoVariety
        fields = EDITABLE_FIELDS

    def clean_name(self):
        # La restricción única es sobre el nombre normalizado, que el formulario no muestra:
        # sin esta revisión el repetido llegaría a la base como un error sin explicar.
        name = self.cleaned_data["name"]
        if name_taken(name, exclude_id=self.instance.pk):
            raise forms.ValidationError(DuplicateVarietyName.default_detail)
        return name


@admin.register(CacaoVariety)
class CacaoVarietyAdmin(admin.ModelAdmin):
    form = CacaoVarietyAdminForm
    list_display = ("name", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "name_normalized")
    fields = EDITABLE_FIELDS

    # Los permisos siguen al de la API y no a los que Django genera, para que un mismo rol pueda
    # lo mismo en los dos lados. Eliminar es solo para lo registrado por error: una variedad que
    # alguna ficha usa no se puede eliminar, se desactiva.
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_PERMISSION)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_PERMISSION)

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_PERMISSION)

    def has_add_permission(self, request):
        return request.user.has_perm(MANAGE_PERMISSION)

    # Todo pasa por los servicios, para normalizar el nombre y dejar el historial como la API.
    def save_model(self, request, obj, form, change):
        data = {name: form.cleaned_data[name] for name in EDITABLE_FIELDS}
        if change:
            saved = update_variety(request.user, obj.pk, data)
        else:
            saved = create_variety(request.user, data)
        # El admin sigue usando `obj` para el mensaje, el registro de cambios y la redirección.
        obj.pk = saved.pk
        obj.name = saved.name
        obj.name_normalized = saved.name_normalized
        obj.updated_at = saved.updated_at
        obj._state.adding = False

    def delete_model(self, request, obj):
        delete_variety(request.user, obj)

    def delete_queryset(self, request, queryset):
        for variety in queryset:
            delete_variety(request.user, variety)


@admin.register(PlotCharacterizationAuditEvent)
class PlotCharacterizationAuditEventAdmin(admin.ModelAdmin):
    """El historial de las fichas con los valores de cada versión, de solo lectura."""

    list_display = ("plot", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("plot", "actor")
    readonly_fields = ("plot", "action", "actor", "changed_fields", "snapshot", "occurred_at")

    # Solo superusuarios: el admin no filtra por productor, así que con el permiso de la API
    # (`plots.view_plot`) un empleado de un productor vería las fichas de todos, y la asociación
    # no lee fichas.
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
