import pytest
from django.apps import apps
from django.db import connection, models

from apps.facilities.models import PostharvestFacility

from .factories import PostharvestFacilityFactory


@pytest.fixture
def facility_usage_table(db):
    """Una tabla de prueba que apunta a un elemento, como lo harán la fermentación y el secado.

    Devuelve una función que registra un uso de un elemento. La tabla se crea con el editor de
    esquema dentro de la transacción de la prueba, que la deshace al terminar, y el modelo sale del
    registro de modelos para no afectar a las demás pruebas.
    """

    class FacilityUsage(models.Model):
        facility = models.ForeignKey(
            PostharvestFacility, on_delete=models.PROTECT, related_name="+"
        )

        class Meta:
            app_label = "facilities"
            db_table = "facilities_test_facility_usage"

    with connection.schema_editor() as editor:
        editor.create_model(FacilityUsage)
    PostharvestFacility._meta._expire_cache()
    try:
        yield lambda facility: FacilityUsage.objects.create(facility=facility)
    finally:
        # La tabla desaparece con la transacción de la prueba; aquí solo se retira el modelo.
        apps.all_models["facilities"].pop("facilityusage", None)
        apps.clear_cache()
        PostharvestFacility._meta._expire_cache()


@pytest.fixture
def used_facility(facility_usage_table):
    """Un elemento que una tabla de prueba ya usa."""
    facility = PostharvestFacilityFactory()
    facility_usage_table(facility)
    return facility
