from django.contrib import admin, messages

from apps.common.admin import (
    ServiceAdminMixin,
    ServiceFailed,
    SuperuserReadOnlyAdminMixin,
    VersionedAdminForm,
    run_service,
)
from apps.common.ownership import owner_filter

from .fields import FIELDS
from .models import PostharvestParameters, PostharvestParametersAuditEvent
from .serializers import PostharvestValuesInputSerializer
from .services.reset import reset_parameters
from .services.save import save_parameters


class PostharvestParametersAdminForm(VersionedAdminForm):
    class Meta:
        model = PostharvestParameters
        fields = FIELDS

    def clean(self):
        cleaned = super().clean()
        # Las mismas reglas y mensajes que la API, para no tener una segunda copia que se aparte.
        values = {name: cleaned[name] for name in FIELDS if name in cleaned}
        if len(values) == len(FIELDS):
            rules = PostharvestValuesInputSerializer(data=values)
            if not rules.is_valid():
                for name, errors in rules.errors.items():
                    self.add_error(name if name in FIELDS else None, errors)
        return cleaned


@admin.register(PostharvestParameters)
class PostharvestParametersAdmin(ServiceAdminMixin, admin.ModelAdmin):
    form = PostharvestParametersAdminForm
    list_display = ("producer", "updated_at", "updated_by", "version")
    list_select_related = ("producer", "updated_by")
    readonly_fields = ("producer", "updated_by", "version", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("producer", *FIELDS, "expected_version")}),
        ("Registro", {"fields": ("updated_by", "version", "created_at", "updated_at")}),
    )
    actions = ("reset_to_baseline",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(**owner_filter(request.user))

    # Un productor sin parámetros ya usa la línea base: no hay nada que dar de alta. Y volver a
    # ella es restablecer, que deja su evento en el historial, no un borrado.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        run_service(
            save_parameters,
            request.user,
            obj.pk,
            form.cleaned_data["expected_version"],
            {name: form.cleaned_data[name] for name in FIELDS},
        )

    @admin.action(description="Restablecer la línea base", permissions=["change"])
    def reset_to_baseline(self, request, queryset):
        reset = skipped = 0
        for parameters in queryset:
            try:
                run_service(reset_parameters, request.user, parameters.pk, parameters.version)
                reset += 1
            except ServiceFailed:
                skipped += 1
        self.message_user(request, f"Parámetros restablecidos: {reset}.", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} cambiaron mientras tanto y se omitieron; vuelve a intentarlo.",
                messages.WARNING,
            )


@admin.register(PostharvestParametersAuditEvent)
class PostharvestParametersAuditEventAdmin(SuperuserReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "producer", "action", "actor", "version")
    list_filter = ("action",)
    list_select_related = ("producer", "actor")
