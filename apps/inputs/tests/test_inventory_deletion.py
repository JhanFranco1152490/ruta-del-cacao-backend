from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.inputs.models import AgriculturalInput, InputMovement
from apps.inputs.services import register_movement
from apps.producers.exceptions import ProducerHasRecords
from apps.producers.models import Producer
from apps.producers.services import delete_producer
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def stocked(producer):
    """Una finca con un insumo que ya tiene una entrada registrada."""
    farm = FarmFactory(producer=producer)
    item = AgriculturalInputFactory(producer=producer, unit="ml")
    register_movement(
        UserFactory(producer=producer),
        {
            "input_id": item.pk,
            "farm_id": farm.pk,
            "kind": "entry",
            "quantity": Decimal("10"),
            "occurred_on": timezone.localdate(),
        },
    )
    return farm, item


def test_a_farm_with_input_movements_is_not_deleted(auth_client, producer, stocked):
    farm, _ = stocked

    response = auth_client(make_producer_owner(producer)).delete(
        f"/api/farms/{farm.pk}?expected_version={farm.version}"
    )

    assert response.status_code == 409
    assert response.data["code"] == "farm_has_records"
    assert Farm.objects.filter(pk=farm.pk).exists()


def test_a_farm_without_movements_is_still_deleted(auth_client, producer):
    farm = FarmFactory(producer=producer)
    AgriculturalInputFactory(producer=producer)

    response = auth_client(make_producer_owner(producer)).delete(
        f"/api/farms/{farm.pk}?expected_version={farm.version}"
    )

    assert response.status_code == 204


def test_a_producer_with_movements_is_not_deleted_and_nothing_is_lost(producer, stocked):
    _, item = stocked
    free = AgriculturalInputFactory(producer=producer, name="Sin uso")

    with pytest.raises(ProducerHasRecords):
        delete_producer(UserFactory(is_superuser=True), producer.pk, producer.version)

    assert Producer.objects.filter(pk=producer.pk).exists()
    assert AgriculturalInput.objects.filter(pk__in=[item.pk, free.pk]).count() == 2
    assert InputMovement.objects.count() == 1
