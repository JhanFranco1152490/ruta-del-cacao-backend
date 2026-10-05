import pytest

from apps.crops.models import CacaoVariety


@pytest.fixture
def empty_catalog(db):
    """El catálogo sin las variedades iniciales.

    La migración las carga, pero las pruebas con `transaction=True` vacían las tablas al
    terminar: según el orden en que corran, las pruebas verían o no esas filas. Se parte de un
    catálogo vacío para que lo que se lista sea solo lo que la prueba creó.
    """
    CacaoVariety.objects.all().delete()
