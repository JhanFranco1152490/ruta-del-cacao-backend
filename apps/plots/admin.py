from django.contrib import admin

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.ownership import owner_filter

from .models import Plot, PlotAuditEvent
from .services.content import UPDATABLE_FIELDS
from .services.delete import delete_plot
from .services.update import update_plot


class PlotAdminForm(VersionedAdminForm):
    class Meta:
        model = Plot
        fields = UPDATABLE_FIELDS


@admin.register(Plot)
class PlotAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = PlotAdminForm
    list_display = (
        "code",
        "farm",
        "producer",
        "area_hectares",
        "measured_area_hectares",
        "is_active",
    )
    list_filter = ("is_active",)
    list_select_related = ("farm__producer",)
    search_fields = (
        "code",
        "farm__name__unaccent",
        "farm__producer__member_code",
        "farm__producer__identity_document",
        "farm__producer__first_name__unaccent",
        "farm__producer__last_name__unaccent",
    )
    # El contorno se dibuja en la pantalla con el mapa: un polígono escrito a mano en un campo de
    # texto es la vía más fácil para dejar una parcela superpuesta o sin sentido.
    readonly_fields = (
        "farm",
        "producer",
        "boundary",
        "measured_area_hectares",
        "version",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("farm", "producer", *UPDATABLE_FIELDS, "expected_version")}),
        ("Contorno", {"fields": ("boundary", "measured_area_hectares")}),
        ("Registro", {"fields": ("version", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request).filter(**owner_filter(request.user, "farm__producer_id"))
        )

    @admin.display(description="Productor", ordering="farm__producer__last_name")
    def producer(self, plot):
        return plot.farm.producer

    # El alta es de la aplicación: lleva el contorno dibujado con el mapa y las reglas de área.
    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        saved = run_service(
            update_plot,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in UPDATABLE_FIELDS},
        )
        obj.version = saved.version
        obj.updated_at = saved.updated_at

    def delete_model(self, request, obj):
        run_service(delete_plot, request.user, obj.pk, obj.version)


@admin.register(PlotAuditEvent)
class PlotAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El historial de las parcelas, de solo lectura; sobrevive a la parcela eliminada."""

    list_display = ("plot_code", "action", "area_hectares", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    search_fields = ("plot_code",)
