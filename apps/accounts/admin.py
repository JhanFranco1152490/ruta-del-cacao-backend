from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.common.admin import ReadOnlyAdminMixin, ServiceAdminMixin, run_service

from .access import roles_of
from .auth.services import revoke_all_sessions
from .models import AccountManagementEvent, AuthenticationEvent, Role, User
from .requests import request_id_from
from .scope import visible_users
from .system_roles import PRODUCER
from .users.services import delete_account, set_account_status, update_account

# Lo que `update_account` guarda. Los datos personales de una cuenta Productor los gobierna su
# expediente, así que en esa cuenta el admin los muestra sin dejar editarlos, como la API.
ACCOUNT_FIELDS = ("email", "document_type", "identity_document", "first_name", "last_name")
PERSONAL_FIELDS = ("document_type", "identity_document", "first_name", "last_name")
# Banderas técnicas sin invariantes de negocio: las toca solo un superusuario.
TECHNICAL_FIELDS = ("is_staff", "is_superuser", "user_permissions")

# token_blacklist se registra sola en el admin y se instala antes que esta app, así que su
# registro ya ocurrió al importar este módulo. La ficha de OutstandingToken muestra el token de
# renovación completo (válido 7 días) y el admin de BlacklistedToken permite borrar filas, lo
# que reactiva un token revocado: ninguno debe ser alcanzable desde el admin.
admin.site.unregister(OutstandingToken)
admin.site.unregister(BlacklistedToken)

# Un rol es un `Group` con dueño e invariantes propias (ver `models.Role`): tocar el grupo
# directo desde aquí las saltaría por completo. `Role` reemplaza a `Group` en el admin, de
# solo lectura, porque crearlos o editarlos pasa por `roles/services.py`, no por aquí.
admin.site.unregister(Group)


@admin.register(User)
class CustomUserAdmin(ServiceAdminMixin, UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "document_type", "identity_document", "is_active", "is_staff")
    search_fields = ("email", "identity_document", "first_name", "last_name")
    # El último inicio de sesión decide si una cuenta se puede eliminar: no se edita a mano.
    readonly_fields = ("producer", "role_names", "last_login", "date_joined")
    filter_horizontal = ("user_permissions",)
    fieldsets = (
        (None, {"fields": ("email", "document_type", "identity_document", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "producer",
                    "role_names",
                    "user_permissions",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )

    # Los permisos siguen a los de la API y no a los que Django genera, para que un mismo rol
    # pueda lo mismo en los dos lados.
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("accounts.users_view") or self.has_change_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("accounts.users_update")

    # Sin alta: crear una cuenta asigna rol y productor y envía la activación, y desde aquí
    # quedaría una sin rol ni productor, que rompe «toda cuenta tiene al menos un rol». Los
    # caminos son la API, `create_association_admin` y `createsuperuser`.
    def has_add_permission(self, request):
        return False

    # Eliminar pasa por `delete_account` (solo una cuenta que nunca inició sesión). Las cuentas
    # técnicas están fuera del modelo de negocio y no se eliminan desde aquí.
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser:
            return False
        return request.user.has_perm("accounts.users_delete")

    def get_queryset(self, request):
        # La cuenta técnica ve todas, también las técnicas; cualquier otra, las que alcanza.
        if request.user.is_superuser:
            return super().get_queryset(request)
        return visible_users(request.user)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly.extend(TECHNICAL_FIELDS)
        if obj is not None and not obj.is_superuser:
            if obj.groups.filter(role__code=PRODUCER).exists():
                readonly.extend(PERSONAL_FIELDS)
        return readonly

    def save_model(self, request, obj, form, change):
        if User.objects.filter(pk=obj.pk, is_superuser=True).exists():
            # Una cuenta técnica no entra en `visible_users`: sus datos se editan directo.
            super().save_model(request, obj, form, change)
            return
        request_id = request_id_from(request)
        changed = set(form.changed_data)
        data = {name: form.cleaned_data[name] for name in ACCOUNT_FIELDS if name in changed}
        if data:
            run_service(update_account, request.user, obj.pk, data, request_id)
        if "is_active" in changed:
            status = "active" if form.cleaned_data["is_active"] else "inactive"
            run_service(set_account_status, request.user, obj.pk, status, request_id)
        flags = {
            name: form.cleaned_data[name]
            for name in ("is_staff", "is_superuser")
            if name in changed
        }
        if flags:
            User.objects.filter(pk=obj.pk).update(**flags)
        obj.refresh_from_db()

    def delete_model(self, request, obj):
        run_service(delete_account, request.user, obj.pk, request_id_from(request))

    def user_change_password(self, request, id, form_url=""):
        # Una contraseña nueva no debe dejar abiertas las sesiones de la anterior: quien la
        # conocía seguiría dentro.
        before = User.objects.filter(pk=id).values_list("password", flat=True).first()
        response = super().user_change_password(request, id, form_url)
        user = User.objects.filter(pk=id).first()
        if user is not None and before is not None and user.password != before:
            revoke_all_sessions(user)
        return response

    @admin.display(description="Roles")
    def role_names(self, user):
        # Los roles se conceden y se quitan por la API de HU-03 (con sus invariantes: nadie
        # concede más de lo que tiene, siempre queda un administrador); editar `groups` aquí
        # las saltaría por completo.
        return ", ".join(role.name for role in roles_of(user)) or "—"


@admin.register(AuthenticationEvent)
class AuthenticationEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("event_type", "outcome", "user", "occurred_at")
    list_filter = ("event_type", "outcome")
    readonly_fields = ("event_type", "outcome", "user", "request_id", "occurred_at")


@admin.register(Role)
class RoleAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "kind", "code", "producer")
    list_filter = ("kind",)
    search_fields = ("name", "code")


@admin.register(AccountManagementEvent)
class AccountManagementEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("event_type", "actor", "target_user", "occurred_at")
    list_filter = ("event_type",)
    readonly_fields = (
        "event_type",
        "actor",
        "target_user",
        "target_role_id",
        "request_id",
        "occurred_at",
    )
