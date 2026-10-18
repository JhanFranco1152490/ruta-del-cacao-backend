from django import forms
from django.contrib import admin

from apps.common.admin import (
    ReadOnlyInlineMixin,
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    run_service,
)

from .exceptions import DuplicatePestDiseaseName
from .models import (
    Detection,
    HealthEvidenceAuditEvent,
    PestDisease,
    PhytosanitaryMonitoring,
    PhytosanitaryMonitoringEvidence,
    PhytosanitaryTreatment,
    PhytosanitaryTreatmentEvidence,
)
from .services.catalog import (
    EDITABLE_FIELDS,
    create_pest_disease,
    delete_pest_disease,
    name_taken,
    update_pest_disease,
)

MANAGE_PERMISSION = "health.manage_pestdisease"


class PestDiseaseAdminForm(forms.ModelForm):
    class Meta:
        model = PestDisease
        fields = EDITABLE_FIELDS

    def clean_name(self):
        # La restricción única es sobre el nombre normalizado, que el formulario no muestra:
        # sin esta revisión el repetido llegaría a la base como un error sin explicar.
        name = self.cleaned_data["name"]
        if name_taken(name, exclude_id=self.instance.pk):
            raise forms.ValidationError(DuplicatePestDiseaseName.default_detail)
        return name


@admin.register(PestDisease)
class PestDiseaseAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = PestDiseaseAdminForm
    list_display = ("name", "kind", "scientific_name", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "search_normalized")
    fields = EDITABLE_FIELDS

    # Los permisos siguen al de la API y no a los que Django genera. Eliminar es solo para lo
    # registrado por error: una que algún monitoreo usa no se elimina, se desactiva.
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_PERMISSION)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_PERMISSION)

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_PERMISSION)

    def has_add_permission(self, request):
        return request.user.has_perm(MANAGE_PERMISSION)

    def save_model(self, request, obj, form, change):
        data = {name: form.cleaned_data[name] for name in EDITABLE_FIELDS}
        if change:
            saved = run_service(update_pest_disease, obj.pk, data)
        else:
            saved = run_service(create_pest_disease, data)
        # El admin sigue usando `obj` para el mensaje, el registro de cambios y la redirección.
        obj.pk = saved.pk
        obj.name = saved.name
        obj.normalized_name = saved.normalized_name
        obj.updated_at = saved.updated_at
        obj._state.adding = False

    def delete_model(self, request, obj):
        run_service(delete_pest_disease, obj)


class DetectionInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = Detection
    fields = ("pest_disease", "other_description", "affected_units", "incidence")
    readonly_fields = fields


EVIDENCE_FIELDS = ("file_name", "content_type", "size", "uploaded_by", "uploaded_at")


class MonitoringEvidenceInline(ReadOnlyInlineMixin, admin.TabularInline):
    # Solo los datos de la foto: el archivo se ve desde la aplicación, que revisa el alcance.
    model = PhytosanitaryMonitoringEvidence
    fields = EVIDENCE_FIELDS
    readonly_fields = fields


class TreatmentEvidenceInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PhytosanitaryTreatmentEvidence
    fields = EVIDENCE_FIELDS
    readonly_fields = fields


@admin.register(PhytosanitaryMonitoring)
class PhytosanitaryMonitoringAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El resultado de los monitoreos con sus detecciones, de solo lectura: un monitoreo
    registrado no se corrige."""

    list_display = ("activity", "sampling_unit", "evaluated_units", "no_presence", "created_at")
    list_filter = ("sampling_unit", "no_presence")
    list_select_related = ("activity__plot__farm",)
    search_fields = ("activity__plot__name__unaccent", "activity__plot__farm__name__unaccent")
    readonly_fields = (
        "activity",
        "sampling_unit",
        "evaluated_units",
        "sampling_method",
        "notes",
        "no_presence",
        "created_at",
    )
    inlines = [DetectionInline, MonitoringEvidenceInline]


@admin.register(PhytosanitaryTreatment)
class PhytosanitaryTreatmentAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Qué detección atiende cada control y qué se hizo, de solo lectura: el control se edita
    como actividad."""

    list_display = ("activity", "detection", "method")
    list_filter = ("method",)
    list_select_related = ("activity__plot", "detection__pest_disease")
    readonly_fields = ("activity", "detection", "planned_input", "method", "method_description")
    inlines = [TreatmentEvidenceInline]


@admin.register(HealthEvidenceAuditEvent)
class HealthEvidenceAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Quién adjuntó o eliminó cada foto, de solo lectura; sobrevive a la foto."""

    list_display = ("evidence_ref", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    readonly_fields = ("evidence_ref", "activity_ref", "action", "actor", "occurred_at")
