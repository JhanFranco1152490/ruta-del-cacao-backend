import pytest
from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as ApiValidationError

from apps.common.admin import ServiceFailed, describe_failure, run_service
from apps.common.exceptions import ApiError

# Modelos del dominio que no tienen admin, cada uno con su motivo. Está vacío a propósito: un
# modelo nuevo que no se registre en el admin debe fallar aquí y no quedar fuera por olvido.
WITHOUT_ADMIN: dict[str, str] = {}


def domain_models():
    return [
        model
        for config in apps.get_app_configs()
        if config.name.startswith("apps.")
        for model in config.get_models()
    ]


def test_there_are_domain_models_to_check():
    assert len(domain_models()) > 15


def shown_in_the_admin():
    """Los modelos registrados y los que se ven dentro de la ficha de otro (siembras, insumos de
    una labor)."""
    registered = set(admin.site._registry)
    inlined = {
        inline.model
        for model_admin in admin.site._registry.values()
        for inline in model_admin.inlines
    }
    return registered | inlined


def test_every_domain_model_has_an_admin():
    shown = shown_in_the_admin()
    missing = [
        model._meta.label
        for model in domain_models()
        if model not in shown and model._meta.label not in WITHOUT_ADMIN
    ]

    assert missing == []


def test_the_models_without_an_admin_are_still_real_models():
    labels = {model._meta.label for model in domain_models()}

    assert set(WITHOUT_ADMIN) <= labels


class StaleThing(ApiError):
    default_detail = "El registro cambió mientras tanto."


class WithFields(ApiError):
    default_detail = "Datos no válidos."

    def __init__(self):
        super().__init__(fields={"name": ["Ya existe.", "Ya existe."], "area": ["Es muy grande."]})


def test_an_api_error_is_described_with_its_message_and_the_message_of_each_field():
    assert describe_failure(StaleThing()) == "El registro cambió mientras tanto."
    assert describe_failure(WithFields()) == "Datos no válidos. Ya existe. Es muy grande."


def test_a_validation_error_is_described_with_every_message():
    api = ApiValidationError({"code": ["Repetido."], "area": ["Muy grande.", "Negativa."]})
    django = DjangoValidationError({"code": ["Repetido."]})

    assert describe_failure(api) == "Repetido. Muy grande. Negativa."
    assert describe_failure(django) == "Repetido."


def test_an_unexpected_error_is_not_swallowed():
    with pytest.raises(ZeroDivisionError):
        describe_failure(ZeroDivisionError())


def test_run_service_returns_what_the_service_returns():
    assert run_service(lambda a, b=0: a + b, 2, b=3) == 5


def test_run_service_turns_a_business_error_into_a_failure_with_its_message():
    def service():
        raise StaleThing()

    with pytest.raises(ServiceFailed, match="El registro cambió mientras tanto."):
        run_service(service)


def test_run_service_lets_a_real_bug_through():
    def service():
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        run_service(service)
