from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.inputs.exceptions import InputHasRecords, InputUnitLocked
from apps.inputs.services import delete_input, get_input, register_movement, update_input
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def member():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def stocked(member):
    """Un insumo con una entrada registrada en una finca."""
    item = AgriculturalInputFactory(
        producer=member.producer, unit="ml", package_type="tub", package_size=Decimal("100")
    )
    farm = FarmFactory(producer=member.producer)
    register_movement(
        member,
        {
            "input_id": item.pk,
            "farm_id": farm.pk,
            "kind": "entry",
            "quantity": Decimal("300"),
            "occurred_on": date.today(),
        },
    )
    return item


def test_an_input_with_movements_has_records(member, stocked):
    assert get_input(member, stocked.pk).has_records is True


def test_the_unit_of_an_input_with_movements_is_locked_but_the_package_is_not(member, stocked):
    with pytest.raises(InputUnitLocked):
        update_input(member, stocked.pk, 1, {"unit": "l"})

    updated = update_input(member, stocked.pk, 1, {"package_size": Decimal("250")})
    assert updated.package_size == Decimal("250.000")


def test_an_input_with_movements_cannot_be_deleted(member, stocked):
    with pytest.raises(InputHasRecords):
        delete_input(member, stocked.pk, 1)


def test_deactivating_an_input_keeps_its_stock(member, stocked):
    update_input(member, stocked.pk, 1, {"is_active": False})

    assert stocked.stocks.get().quantity == Decimal("300.000")
