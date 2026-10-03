from django.apps import AppConfig
from django.apps import apps as app_registry
from django.db.models.signals import post_migrate, post_save


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from .auth import schema  # noqa: F401  (registra la extensión de drf-spectacular)

        # Los roles del sistema usan permisos de otras apps, que Django crea en el post_migrate
        # de cada una, en el orden de INSTALLED_APPS. Solo al llegarle el turno a la última ya
        # existen todos; conectarse a esta misma app, o a una fija, sería demasiado pronto en
        # cuanto se agregue otra app después.
        post_migrate.connect(
            _sync_system_roles, sender=last_app_with_models(app_registry.get_app_configs())
        )

        # Sin importar apps.producers (ninguna app importa de otra, ver AGENTS.md): el modelo
        # se obtiene del registro de apps, ya poblado para cuando corre ready(). Como esto pasa
        # dentro de Producer.save(), a su vez dentro de la transacción de create_producer(), un
        # correo o documento repetido revierte también el alta del productor.
        post_save.connect(
            _create_producer_account, sender=app_registry.get_model("producers", "Producer")
        )
        # Lo que esta app elimina cuando se elimina un productor creado por error.
        from apps.common.producer_dependents import register_dependent

        from .producer_dependent import accounts_dependent

        register_dependent(accounts_dependent)


def last_app_with_models(app_configs):
    # Django no emite post_migrate para una app sin modelos: si la última instalada no tiene,
    # conectarse a ella dejaría los roles sin sincronizar nunca.
    return [config for config in app_configs if config.models_module is not None][-1]


def _sync_system_roles(sender, **kwargs):
    from .system_roles import sync_system_roles

    sync_system_roles()


def _create_producer_account(sender, instance, created, **kwargs):
    if not created:
        return
    from .users.services import create_producer_account_automatically

    create_producer_account_automatically(instance)
