from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import AuthenticationEvent, User

# token_blacklist se registra sola en el admin y se instala antes que esta app, así que su
# registro ya ocurrió al importar este módulo. La ficha de OutstandingToken muestra el token de
# renovación completo (válido 7 días) y el admin de BlacklistedToken permite borrar filas, lo
# que reactiva un token revocado: ninguno debe ser alcanzable desde el admin.
admin.site.unregister(OutstandingToken)
admin.site.unregister(BlacklistedToken)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "document_type", "identity_document", "is_active", "is_staff")
    search_fields = ("email", "identity_document", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "document_type", "identity_document", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name")}),
        (
            "Permisos",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
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
