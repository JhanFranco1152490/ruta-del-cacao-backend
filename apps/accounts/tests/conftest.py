import pytest

from apps.accounts.system_roles import sync_system_roles


@pytest.fixture
def system_roles():
    """Siembra los roles del sistema para las pruebas con `transaction=True`.

    Esas pruebas usan una base de datos real sin envolver cada test en una transacción que se
    revierte, así que no heredan la siembra que corre una sola vez al preparar la base de
    pruebas.
    """
    sync_system_roles()
