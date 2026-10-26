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


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    # El hasher de producción es deliberadamente lento (cientos de miles de iteraciones) y cada
    # usuario de prueba lo paga al crearse y al iniciar sesión. En las pruebas no protege nada.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _files_in_memory(settings):
    # Los archivos subidos en las pruebas quedan en memoria y no en la base ni en el disco. Las
    # pruebas del almacenamiento en la base lo instancian directamente.
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    }
    # Una subida grande queda en memoria y no en un archivo temporal: el almacenamiento en memoria
    # borra ese archivo mientras sigue abierto, y en Windows eso falla. El almacenamiento en la
    # base no lo borra; su prueba con un archivo temporal está en `test_storage.py`.
    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


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
