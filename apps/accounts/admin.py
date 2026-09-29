from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .access import roles_of
from .models import AccountManagementEvent, AuthenticationEvent, Role, User

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
class CustomUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "document_type", "identity_document", "is_active", "is_staff")
    search_fields = ("email", "identity_document", "first_name", "last_name")
    readonly_fields = ("producer", "role_names")
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

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "document_type",
                    "identity_document",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    @admin.display(description="Roles")
    def role_names(self, user):
        # Los roles se conceden y se quitan por la API de HU-03 (con sus invariantes: nadie
        # concede más de lo que tiene, siempre queda un administrador); editar `groups` aquí
        # las saltaría por completo.
        return ", ".join(role.name for role in roles_of(user)) or "—"


@admin.register(AuthenticationEvent)
class AuthenticationEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "outcome", "user", "occurred_at")
    list_filter = ("event_type", "outcome")
    readonly_fields = ("event_type", "outcome", "user", "request_id", "occurred_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "code", "producer")
    list_filter = ("kind",)
    search_fields = ("name", "code")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AccountManagementEvent)
class AccountManagementEventAdmin(admin.ModelAdmin):
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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
