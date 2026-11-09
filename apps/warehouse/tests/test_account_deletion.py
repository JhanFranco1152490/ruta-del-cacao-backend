"""Una cuenta que ingresó, corrigió, sacó o anuló en bodega tiene actividad: no se elimina."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.services.entry import correct_entry
from apps.warehouse.services.exits import remove_stock, void_exit
from apps.warehouse.services.moves import move_stock

from .factories import WarehouseFactory
from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return WarehouseEstate()


def delete_account(auth_client, estate, account):
    return auth_client(estate.owner).delete(f"/api/users/{account.pk}")


def other_employee(estate):
    return make_delegate(
        estate.producer,
        ["warehouse.register_entry", "warehouse.register_exit"],
        farm=estate.farm_a,
    )


def test_the_account_that_entered_a_lot_is_not_deleted(auth_client, estate):
    # El ingreso del lote de la finca lo hizo el Encargado de calidad.
    response = delete_account(auth_client, estate, estate.inspector)

    assert (response.status_code, response.data["code"]) == (409, "account_has_activity")
    assert User.objects.filter(pk=estate.inspector.pk).exists()


def test_the_account_that_took_cacao_out_is_not_deleted(auth_client, estate):
    taker = other_employee(estate)
    remove_stock(
        taker,
        estate.stored,
        "g1",
        Decimal("5.0"),
        exit_date=timezone.localdate(),
        reason="sample",
    )

    response = delete_account(auth_client, estate, taker)

    assert (response.status_code, response.data["code"]) == (409, "account_has_activity")


def test_the_account_that_moved_cacao_is_not_deleted(auth_client, estate):
    mover = other_employee(estate)
    annex = WarehouseFactory(farm=estate.farm_a, name="Anexo", name_normalized="anexo")
    move_stock(mover, estate.stored.pk, 1, warehouse_id=annex.pk, location="")

    response = delete_account(auth_client, estate, mover)

    assert (response.status_code, response.data["code"]) == (409, "account_has_activity")


def test_the_account_that_voided_an_exit_is_not_deleted(auth_client, estate):
    voider = other_employee(estate)
    stock_exit = remove_stock(
        estate.inspector,
        estate.stored,
        "g1",
        Decimal("5.0"),
        exit_date=timezone.localdate(),
        reason="sample",
    )
    void_exit(voider, estate.stored.pk, stock_exit.pk, "Error")

    response = delete_account(auth_client, estate, voider)

    assert (response.status_code, response.data["code"]) == (409, "account_has_activity")


def test_the_account_that_corrected_an_entry_is_not_deleted(auth_client, estate):
    corrector = other_employee(estate)
    correct_entry(corrector, estate.stored.pk, 1, {"location": "Estante 8"})

    response = delete_account(auth_client, estate, corrector)

    assert (response.status_code, response.data["code"]) == (409, "account_has_activity")


def test_an_account_without_movements_is_deleted(auth_client, estate):
    idle = UserFactory(producer=estate.producer)

    response = delete_account(auth_client, estate, idle)

    assert response.status_code == 204
