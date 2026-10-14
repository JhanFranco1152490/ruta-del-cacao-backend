from django.contrib import admin

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.ownership import owner_filter

from .models import AgriculturalInput, AgriculturalInputAuditEvent, InputMovement, InputStock
from .services.create import CONTENT_FIELDS
from .services.delete import delete_input
from .services.update import update_input


class AgriculturalInputAdminForm(VersionedAdminForm):
    class Meta:
        model = AgriculturalInput
        fields = CONTENT_FIELDS


@admin.register(AgriculturalInput)
class AgriculturalInputAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = AgriculturalInputAdminForm
    list_display = ("name", "producer", "input_type", "unit", "is_active")
    list_filter = ("input_type", "unit", "is_active")
    list_select_related = ("producer",)
    search_fields = (
        "name__unaccent",
        "producer__member_code",
        "producer__identity_document",
        "producer__first_name__unaccent",
        "producer__last_name__unaccent",
    )
    readonly_fields = ("producer", "version", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("producer", *CONTENT_FIELDS, "expected_version")}),
        ("Registro", {"fields": ("version", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(**owner_filter(request.user))

    # El alta lleva el productor dueño y es de la aplicación. La unidad de un insumo ya usado no
    # cambia: `update_input` lo rechaza con su motivo.
    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        saved = run_service(
            update_input,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in CONTENT_FIELDS},
        )
        obj.version = saved.version
        obj.updated_at = saved.updated_at

    def delete_model(self, request, obj):
        run_service(delete_input, request.user, obj.pk, obj.version)


@admin.register(InputStock)
class InputStockAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Las existencias de cada insumo en cada finca, de solo lectura: son el resultado de sus
    movimientos y editarlas a mano dejaría el inventario sin explicación."""

    list_display = ("input", "farm", "quantity", "last_count_date")
    list_select_related = ("input", "farm")
    search_fields = ("input__name__unaccent", "farm__name__unaccent")


@admin.register(InputMovement)
class InputMovementAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """Los movimientos del inventario (entradas, conteos y salidas por actividad), de solo
    lectura: un error se corrige con un conteo desde la aplicación."""

    list_display = ("occurred_on", "input", "farm", "kind", "quantity", "actor")
    list_filter = ("kind",)
    list_select_related = ("input", "farm", "actor")
    search_fields = ("input__name__unaccent", "farm__name__unaccent")


@admin.register(AgriculturalInputAuditEvent)
class AgriculturalInputAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
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
