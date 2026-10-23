import pytest
from django.apps import apps
from django.db import connection, models

from apps.buyers.models import Buyer

from .factories import BuyerFactory


@pytest.fixture
def buyer_usage_table(db):
    """Una tabla de prueba que apunta a un comprador, como lo harán las ventas.

    Devuelve una función que registra un uso de un comprador. La tabla se crea con el editor de
    esquema dentro de la transacción de la prueba, que la deshace al terminar, y el modelo sale del
    registro de modelos para no afectar a las demás pruebas.
    """

    class BuyerUsage(models.Model):
        buyer = models.ForeignKey(Buyer, on_delete=models.PROTECT, related_name="+")

        class Meta:
            app_label = "buyers"
            db_table = "buyers_test_buyer_usage"

    with connection.schema_editor() as editor:
        editor.create_model(BuyerUsage)
    Buyer._meta._expire_cache()
    try:
        yield lambda buyer: BuyerUsage.objects.create(buyer=buyer)
    finally:
        # La tabla desaparece con la transacción de la prueba; aquí solo se retira el modelo.
        apps.all_models["buyers"].pop("buyerusage", None)
        apps.clear_cache()
        Buyer._meta._expire_cache()


@pytest.fixture
def used_buyer(buyer_usage_table):
    """Un comprador que una tabla de prueba ya usa, como uno con ventas."""
    buyer = BuyerFactory()
    buyer_usage_table(buyer)
    return buyer
