from django.apps import AppConfig
from django.apps import apps as app_registry
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from . import schema  # noqa: F401  (registra la extensión de drf-spectacular)

        # `producers` es la última app de INSTALLED_APPS: cuando le llega su turno en el
        # post_migrate, los permisos de todas las apps (incluidos los suyos, que usa el rol
        # Administrador) ya existen. Conectarse al de esta misma app sería demasiado pronto.
        post_migrate.connect(_sync_system_roles, sender=app_registry.get_app_config("producers"))


def _sync_system_roles(sender, **kwargs):
    from .system_roles import sync_system_roles

    sync_system_roles()
