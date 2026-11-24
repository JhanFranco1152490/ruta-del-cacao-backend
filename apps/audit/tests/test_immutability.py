"""Nada de la bitácora se edita ni se elimina: el admin de cada historial que la forma es de solo
lectura, también para el superusuario."""

import pytest
from django.apps import apps
from django.contrib import admin
from django.test import RequestFactory

from apps.accounts.tests.factories import UserFactory
from apps.common.audit import AuditEventBase

pytestmark = pytest.mark.django_db

# Los historiales de la unidad productiva que no entran en la bitácora (son de la asociación o
# tienen su propia pantalla) también son de solo lectura, pero no los fija esta prueba.
OUTSIDE_THE_LOG = {
    "crops.CacaoVarietyAuditEvent",
    "postharvest_parameters.PostharvestParametersAuditEvent",
}


def histories():
    found = [
        model
        for model in apps.get_models()
        if issubclass(model, AuditEventBase) and model._meta.label not in OUTSIDE_THE_LOG
    ]
    return [*found, apps.get_model("accounts", "AccountManagementEvent")]


def test_the_log_is_formed_by_sixteen_histories():
    assert len(histories()) == 16


@pytest.mark.parametrize("model", histories(), ids=lambda model: model._meta.label)
def test_the_admin_of_each_history_cannot_add_change_or_delete(model):
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)
    model_admin = admin.site._registry[model]

    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
