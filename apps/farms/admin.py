from django import forms
from django.contrib import admin

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.municipalities import list_municipalities
from apps.common.ownership import owner_filter
from apps.common.territorial import MUNICIPALITIES_BY_CODE

from .models import Farm, FarmAuditEvent
from .services.farms import ALLOCATED_AREA, delete_farm, update_farm

# El departamento no se edita: la operación es solo de Norte de Santander. El productor dueño
# tampoco: una finca no cambia de productor.
EDITABLE_FIELDS = (
    "name",
    "municipality_code",
    "details",
    "area_hectares",
    "altitude_masl",
    "latitude",
    "longitude",
    "is_active",
)


class FarmAdminForm(VersionedAdminForm):
    municipality_code = forms.ChoiceField(
        label="Municipio",
        choices=[(item["code"], item["name"]) for item in list_municipalities()],
    )

    class Meta:
        model = Farm
        fields = EDITABLE_FIELDS


@admin.register(Farm)
class FarmAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = FarmAdminForm
    list_display = (
        "name",
        "producer",
        "municipality",
        "area_hectares",
        "allocated_area",
        "is_active",
    )
    list_filter = ("is_active",)
    list_select_related = ("producer",)
    # Una lista larga de productores no cabe en el filtro lateral: se busca por nombre, documento
    # o código, sin tildes, como la API.
    search_fields = (
        "name__unaccent",
        "producer__member_code",
        "producer__identity_document",
        "producer__first_name__unaccent",
        "producer__last_name__unaccent",
    )
    readonly_fields = (
        "producer",
        "department_code",
        "allocated_area",
        "version",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("producer", "department_code", *EDITABLE_FIELDS, "expected_version")}),
        ("Parcelas", {"fields": ("allocated_area",)}),
        ("Registro", {"fields": ("version", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        # Solo la cuenta técnica ve las de todos los productores; cualquier otra, las suyas.
        farms = super().get_queryset(request).filter(**owner_filter(request.user))
        return farms.annotate(allocated_area_hectares=ALLOCATED_AREA)

    @admin.display(description="Municipio", ordering="municipality_code")
    def municipality(self, farm):
        municipality = MUNICIPALITIES_BY_CODE.get(farm.municipality_code)
        return municipality.name if municipality else farm.municipality_code

    @admin.display(description="Área asignada a parcelas (ha)")
    def allocated_area(self, farm):
        return farm.allocated_area_hectares

    # El alta es de la aplicación: lleva la georreferenciación capturada con el mapa y el
    # productor dueño. Editar, activar y eliminar siguen a los permisos de la API.
    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        saved = run_service(
            update_farm,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in EDITABLE_FIELDS},
        )
        obj.version = saved.version
        obj.updated_at = saved.updated_at

    def delete_model(self, request, obj):
        run_service(delete_farm, request.user, obj.pk, obj.version)


@admin.register(FarmAuditEvent)
class FarmAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de las fincas, de solo lectura; sobrevive a la finca eliminada."""

    list_display = ("farm_name", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    search_fields = ("farm_name",)
