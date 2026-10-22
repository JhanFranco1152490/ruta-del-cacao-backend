from django import forms
from django.contrib import messages
from django.contrib.admin.options import ActionLocation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework.exceptions import ValidationError as ApiValidationError

from .exceptions import ApiError

STALE_NOTICE = (
    "Otra persona modificó este registro después de que lo abriste. Recarga la página para ver "
    "los cambios y vuelve a intentarlo."
)


class ReadOnlyAdminMixin:
    # Registros que solo escribe el sistema (eventos, historiales, catálogos sembrados): el admin
    # los consulta pero no los crea, edita ni elimina.

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ApiPermissionAdminMixin:
    # Los permisos siguen al de la API (`api_permission`) y no a los que Django genera, para que un
    # mismo rol pueda lo mismo en los dos lados. Se usa en los catálogos que administra la
    # asociación: ver, registrar, editar y eliminar van juntos.
    api_permission: str

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(self.api_permission)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(self.api_permission)

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm(self.api_permission)

    def has_add_permission(self, request):
        return request.user.has_perm(self.api_permission)


class SuperuserReadOnlyAdminMixin(ReadOnlyAdminMixin):
    # Solo superusuarios: el admin no filtra por productor, así que con el permiso de la API un
    # empleado de un productor vería los registros de todos, y la asociación no lee algunos de
    # ellos.

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser


class ReadOnlyInlineMixin:
    # Lo que cuelga de un registro de solo lectura (las siembras de una ficha, los insumos de una
    # labor): se ve dentro de su ficha y no se toca.
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class VersionedAdminForm(forms.ModelForm):
    # El admin no tiene bloqueo optimista propio: sin la versión con la que se abrió el registro,
    # guardar pisaría en silencio lo que otra persona cambió desde la aplicación.
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    stale_notice = STALE_NOTICE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expected_version"].initial = self.instance.version

    def clean(self):
        cleaned = super().clean()
        version = cleaned.get("expected_version")
        if version is not None and version != self.instance.version:
            raise forms.ValidationError(self.stale_notice)
        return cleaned


class ServiceFailed(Exception):
    """Un servicio rechazó la operación; el mensaje ya está listo para mostrarse en el admin."""


def _flatten(detail) -> list[str]:
    if isinstance(detail, dict):
        return [text for value in detail.values() for text in _flatten(value)]
    if isinstance(detail, (list, tuple)):
        return [text for value in detail for text in _flatten(value)]
    return [str(detail)]


def describe_failure(error: Exception) -> str:
    """El texto del admin para un error de un servicio: el mensaje general y el de cada campo."""
    if isinstance(error, DjangoValidationError):
        texts = list(error.messages)
    elif isinstance(error, ApiError):
        texts = [str(error.detail), *_flatten(error.fields)]
    elif isinstance(error, ApiValidationError):
        texts = _flatten(error.detail)
    else:
        raise error
    return " ".join(dict.fromkeys(texts))


def run_service(service, *args, **kwargs):
    """Llama a un servicio y traduce sus errores de negocio a `ServiceFailed`."""
    try:
        return service(*args, **kwargs)
    except (ApiError, ApiValidationError, DjangoValidationError) as error:
        raise ServiceFailed(describe_failure(error)) from error


class ServiceAdminMixin:
    """Un admin cuyas escrituras pasan por servicios.

    Un servicio que rechaza (versión vieja, código repetido, «tiene registros») lanza
    `ServiceFailed` desde `save_model` o `delete_model`: aquí se deshace la transacción del admin y
    se vuelve a la ficha del registro con el motivo, en vez de una página de error. Tampoco se
    ofrece «Eliminar seleccionados»: eliminar es por registro y con confirmación.
    """

    def _back_to_the_record(self, request, object_id):
        self.message_user(request, request._service_failure, messages.ERROR)
        opts = self.model._meta
        return HttpResponseRedirect(
            reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[object_id])
        )

    def _guard(self, view, request, object_id, *args, **kwargs):
        try:
            return view(request, object_id, *args, **kwargs)
        except ServiceFailed as failure:
            request._service_failure = str(failure)
            return self._back_to_the_record(request, object_id)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return self._guard(super().changeform_view, request, object_id, form_url, extra_context)

    def delete_view(self, request, object_id, extra_context=None):
        return self._guard(super().delete_view, request, object_id, extra_context)

    def get_deleted_objects(self, objs, request):
        # Django bloquea la página si algo protegido apunta al registro; aquí quien decide si se
        # puede eliminar es el servicio (que borra lo que depende de él si nada de eso es
        # importante y, si no, rechaza con su motivo).
        to_delete, model_count, _perms_needed, _protected = super().get_deleted_objects(
            objs, request
        )
        return to_delete, model_count, set(), []

    def get_actions(self, request, action_location=ActionLocation.CHANGE_LIST):
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)
        return actions
