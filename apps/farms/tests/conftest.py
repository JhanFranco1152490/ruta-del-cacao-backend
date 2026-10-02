import pytest
from django.apps import apps
from django.db import connection, models

from apps.farms.models import Farm


@pytest.fixture
def farm_dependent_model(db):
    """Una tabla del negocio que apunta a la finca, como lo harán parcelas o cosechas.

    Todavía no existe ninguna, así que se crea solo para el test que la pide: la regla de
    borrado debe reconocerla sin que nadie la haya listado a mano. La tabla desaparece con la
    transacción del test, y el modelo se retira del registro al terminar para que los demás
    tests no lo vean.
    """

    class FarmDependentRecord(models.Model):
        farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="dependent_records")

        class Meta:
            app_label = "farms"

    with connection.schema_editor() as editor:
        editor.create_model(FarmDependentRecord)
    yield FarmDependentRecord
    del apps.all_models["farms"][FarmDependentRecord._meta.model_name]
    apps.clear_cache()
