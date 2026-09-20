from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuthenticationEvent, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "identity_document", "is_active", "is_staff")
    search_fields = ("email", "identity_document", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "identity_document", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name")}),
        (
            "Permisos",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
        (
            "Seguridad",
            {"fields": ("failed_login_attempts", "lockout_level", "locked_until")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
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
