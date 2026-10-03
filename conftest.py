import pytest
from django.apps import apps
from django.core.cache import cache
from django.db import connection, models
from rest_framework.test import APIClient

from apps.accounts.tests.helpers import csrf_client, open_session


@pytest.fixture(autouse=True)
def _clear_cache():
    # Los límites de solicitudes viven en la caché; sin esto un test hereda los intentos
    # del anterior.
    cache.clear()


@pytest.fixture
def anonymous_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def api_client():
    return csrf_client()


@pytest.fixture
def auth_client(api_client):
    """Devuelve una función que abre una sesión real (cookies JWT) para el usuario dado."""

    def _login(user):
        return open_session(api_client, user)

    return _login


@pytest.fixture
def plain_static_files(settings):
    # Las páginas del admin piden estáticos con manifiesto, que no existen en las pruebas.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def farm_dependent_model(db):
    """Una tabla del negocio que apunta a la finca, como lo harán parcelas o cosechas.

    Todavía no existe ninguna, así que se crea solo para el test que la pide: la regla de
    borrado debe reconocerla sin que nadie la haya listado a mano. La tabla desaparece con la
    transacción del test, y el modelo se retira del registro al terminar para que los demás
    tests no lo vean.
    """

    from apps.farms.models import Farm

    class FarmDependentRecord(models.Model):
        farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="dependent_records")

        class Meta:
            app_label = "farms"

    with connection.schema_editor() as editor:
        editor.create_model(FarmDependentRecord)
    yield FarmDependentRecord
    del apps.all_models["farms"][FarmDependentRecord._meta.model_name]
    apps.clear_cache()
