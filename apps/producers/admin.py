from django import forms
from django.contrib import admin, messages

from apps.common.admin import (
    ServiceAdminMixin,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.municipalities import list_municipalities
from apps.common.territorial import MUNICIPALITIES_BY_CODE

from .exceptions import StaleVersion
from .models import Producer, ProducerAuditEvent
from .services import change_producer_status, delete_producer, update_producer

# Documento, tipo de documento, código y estado no se editan aquí: el documento es la llave
# única del productor y el estado tiene su propio permiso (acciones de la lista).
EDITABLE_FIELDS = ("first_name", "last_name", "phone", "email", "municipality_code", "joined_on")


class ProducerAdminForm(VersionedAdminForm):
    stale_notice = (
        "Otra persona modificó esta ficha después de que la abriste. Recarga la página para ver "
        "los cambios y vuelve a intentarlo."
    )
    municipality_code = forms.ChoiceField(
        label="Municipio",
        choices=[(item["code"], item["name"]) for item in list_municipalities()],
    )

    class Meta:
        model = Producer
        fields = EDITABLE_FIELDS


@admin.register(Producer)
class ProducerAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = ProducerAdminForm
    list_display = ("member_code", "document", "full_name", "municipality", "status", "joined_on")
    list_filter = ("status", "document_type")
    # `unaccent` compara sin tildes, igual que la búsqueda de la API.
    search_fields = (
        "member_code",
        "identity_document",
        "first_name__unaccent",
        "last_name__unaccent",
    )
    readonly_fields = (
        "member_code",
        "document_type",
        "identity_document",
        "status",
        "version",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "member_code",
                    "document_type",
                    "identity_document",
                    *EDITABLE_FIELDS,
                    "expected_version",
                )
            },
        ),
        ("Estado", {"fields": ("status", "version", "created_at", "updated_at")}),
    )
    actions = ("activate", "deactivate")

    @admin.display(description="Documento", ordering="identity_document")
    def document(self, producer):
        return f"{producer.document_type} {producer.identity_document}"

    @admin.display(description="Nombre", ordering="last_name")
    def full_name(self, producer):
        return f"{producer.last_name}, {producer.first_name}"

    @admin.display(description="Municipio", ordering="municipality_code")
    def municipality(self, producer):
        municipality = MUNICIPALITIES_BY_CODE.get(producer.municipality_code)
        return municipality.name if municipality else producer.municipality_code

    # Los permisos siguen a los de la API (`view`, `update`, `change_status`), no a los que
    # Django genera por defecto, para que un mismo rol pueda lo mismo en los dos lados.
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("producers.view") or self.has_change_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("producers.update")

    def has_change_status_permission(self, request):
        return request.user.has_perm("producers.change_status")

    # El alta pasa por la API: asigna el código de asociado y detecta el documento repetido.
    def has_add_permission(self, request):
        return False

    # Eliminar es solo para un productor creado por error: `delete_producer` rechaza al que ya
    # tiene registros importantes, y a ese se le cambia el estado.
    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("producers.delete")

    def save_model(self, request, obj, form, change):
        # El servicio vuelve a comprobar la versión bajo bloqueo y valida como lo hace la API.
        updated = run_service(
            update_producer,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in EDITABLE_FIELDS},
        )
        obj.version = updated.version
        obj.updated_at = updated.updated_at

    def delete_model(self, request, obj):
        run_service(delete_producer, request.user, obj.pk, obj.version)

    @admin.action(
        description="Activar los productores seleccionados", permissions=["change_status"]
    )
    def activate(self, request, queryset):
        self._set_status(request, queryset, Producer.Status.ACTIVE)

    @admin.action(
        description="Desactivar los productores seleccionados", permissions=["change_status"]
    )
    def deactivate(self, request, queryset):
        self._set_status(request, queryset, Producer.Status.INACTIVE)

    def _set_status(self, request, queryset, status):
        changed = skipped = 0
        for producer in queryset.exclude(status=status):
            try:
                change_producer_status(producer.pk, producer.version, status)
                changed += 1
            except StaleVersion:
                skipped += 1
        self.message_user(request, f"Productores actualizados: {changed}.", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} cambiaron mientras tanto y se omitieron; vuelve a intentarlo.",
                messages.WARNING,
            )


@admin.register(ProducerAuditEvent)
class ProducerAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    """El rastro de los productores eliminados, de solo lectura; sobrevive al productor."""

    list_display = ("member_code", "producer_name", "action", "actor", "occurred_at")
    list_filter = ("action",)
    list_select_related = ("actor",)
    search_fields = ("member_code",)
