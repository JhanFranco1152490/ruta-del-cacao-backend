from django import forms
from django.contrib import admin

from apps.common.admin import ReadOnlyInlineMixin, SuperuserReadOnlyAdminMixin

from .exceptions import DuplicateVarietyName
from .models import (
    CacaoVariety,
    CacaoVarietyAuditEvent,
    PlotCharacterization,
    PlotCharacterizationAuditEvent,
    PlotPlanting,
)
from .services import create_variety, delete_variety, name_taken, update_variety

EDITABLE_FIELDS = ("name", "common_names", "description", "is_active")
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
    list_display = ("name", "common_names", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "search_normalized")
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
class PlotCharacterizationAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de las fichas con los valores de cada versión, de solo lectura."""

    list_display = ("plot", "version", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("plot", "actor")
    readonly_fields = (
        "plot",
        "version",
        "action",
        "actor",
        "changed_fields",
        "snapshot",
        "occurred_at",
    )


class PlotPlantingInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PlotPlanting
    fields = ("variety", "planting_date", "tree_count", "propagation", "stage")
    readonly_fields = fields


@admin.register(PlotCharacterization)
class PlotCharacterizationAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """La ficha vigente de cada parcela con sus siembras, de solo lectura: se corrige desde la
    pantalla, que aplica los avisos de coherencia y de densidad."""

    list_display = ("plot", "management_system", "shade_type", "version", "updated_at")
    list_filter = ("management_system", "shade_type")
    list_select_related = ("plot__farm",)
    search_fields = ("plot__code", "plot__farm__name__unaccent")
    inlines = [PlotPlantingInline]


@admin.register(CacaoVarietyAuditEvent)
class CacaoVarietyAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial del catálogo de variedades, de solo lectura; sobrevive a la variedad
    eliminada."""

    list_display = ("variety_name", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    search_fields = ("variety_name",)
