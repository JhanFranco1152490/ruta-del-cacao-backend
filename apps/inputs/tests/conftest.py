import pytest
from django.apps import apps
from django.db import connection, models

from apps.inputs.models import AgriculturalInput

from .factories import AgriculturalInputFactory


@pytest.fixture
def input_usage_table(db):
    """Una tabla de prueba que apunta a un insumo, como lo harán las actividades y los controles.

    Devuelve una función que registra un uso de un insumo. La tabla se crea con el editor de
    esquema dentro de la transacción de la prueba, que la deshace al terminar, y el modelo sale del
    registro de modelos para no afectar a las demás pruebas.
    """

    class InputUsage(models.Model):
        agricultural_input = models.ForeignKey(
            AgriculturalInput, on_delete=models.PROTECT, related_name="+"
        )

        class Meta:
            app_label = "inputs"
            db_table = "inputs_test_input_usage"

    with connection.schema_editor() as editor:
        editor.create_model(InputUsage)
    AgriculturalInput._meta._expire_cache()
    try:
        yield lambda item: InputUsage.objects.create(agricultural_input=item)
    finally:
        # La tabla desaparece con la transacción de la prueba; aquí solo se retira el modelo.
        apps.all_models["inputs"].pop("inputusage", None)
        apps.clear_cache()
        AgriculturalInput._meta._expire_cache()


@pytest.fixture
def used_input(input_usage_table):
    """Un insumo que una tabla de prueba ya usa."""
    item = AgriculturalInputFactory()
    input_usage_table(item)
    return item
