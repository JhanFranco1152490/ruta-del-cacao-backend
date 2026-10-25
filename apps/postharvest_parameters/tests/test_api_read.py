import uuid
from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.common.serializers import full_name
from apps.farms.tests.factories import FarmFactory
from apps.postharvest_parameters.fields import FIELDS
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestParametersFactory

pytestmark = pytest.mark.django_db

URL = "/api/postharvest-parameters"
VIEW = "postharvest_parameters.view_postharvestparameters"

BASELINE_VALUES = {
    "entry_moisture_min_pct": "55.0",
    "entry_moisture_max_pct": "60.0",
    "target_moisture_min_pct": "6.5",
    "target_moisture_max_pct": "7.5",
    "estimated_days_min": 5,
    "estimated_days_max": 7,
    "slow_stall_window_hours": 48,
    "slow_stall_min_drop_pct": "4.0",
    "slow_duration_day": 8,
    "slow_duration_moisture_pct": "10.0",
    "accelerated_day": 3,
    "accelerated_moisture_pct": "15.0",
    "near_target_min_pct": "7.6",
    "near_target_max_pct": "8.5",
    "overdried_moisture_pct": "6.0",
    "first_turn_hours": 48,
    "next_turn_hours": 24,
    "temperature_min_c": "40.0",
    "temperature_max_c": "50.0",
    "ph_min": "4.00",
    "ph_max": "5.50",
}


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


def test_reading_needs_a_session(anonymous_client):
    assert anonymous_client.get(URL).status_code == 401


def test_a_producer_without_parameters_reads_the_baseline(auth_client, owner, producer):
    response = auth_client(owner).get(URL)

    assert response.status_code == 200
    assert response.data["producer_id"] == str(producer.pk)
    assert response.data["is_default"] is True
    assert response.data["values"] == BASELINE_VALUES
    assert response.data["baseline"] == BASELINE_VALUES
    assert response.data["version"] == 0
    assert response.data["updated_at"] is None
    assert response.data["updated_by"] is None


def test_a_producer_with_parameters_reads_them_with_the_baseline_beside(
    auth_client, owner, producer
):
    PostharvestParametersFactory(
        producer=producer,
        slow_duration_day=9,
        overdried_moisture_pct=Decimal("5.5"),
        updated_by=owner,
    )

    response = auth_client(owner).get(URL)

    assert response.data["is_default"] is False
    assert response.data["values"]["slow_duration_day"] == 9
    assert response.data["values"]["overdried_moisture_pct"] == "5.5"
    assert response.data["baseline"] == BASELINE_VALUES
    assert response.data["version"] == 1
    assert response.data["updated_at"] is not None
    assert response.data["updated_by"] == {"id": str(owner.pk), "full_name": full_name(owner)}


def test_the_values_carry_every_parameter(auth_client, owner):
    assert set(auth_client(owner).get(URL).data["values"]) == set(FIELDS)


def test_a_deleted_account_leaves_no_author(auth_client, owner, producer):
    author = UserFactory(producer=producer)
    PostharvestParametersFactory(producer=producer, updated_by=author)
    author.delete()

    assert auth_client(owner).get(URL).data["updated_by"] is None


def test_the_foreman_reads_the_parameters_of_its_producer(auth_client, producer):
    PostharvestParametersFactory(producer=producer, slow_duration_day=9)
    foreman = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)),
        get_system_role(FOREMAN),
    )

    response = auth_client(foreman).get(URL)

    assert response.status_code == 200
    assert response.data["values"]["slow_duration_day"] == 9


def test_an_employee_without_farms_reads_them_too(auth_client, producer):
    # Los parámetros son del productor, no de una finca: no hace falta tener una asignada.
    delegate = make_delegate(producer, [VIEW])

    assert auth_client(delegate).get(URL).status_code == 200


def test_the_parameters_of_another_producer_are_not_reached(auth_client, owner):
    PostharvestParametersFactory(slow_duration_day=9)

    assert auth_client(owner).get(URL).data["is_default"] is True


def test_reading_needs_the_permission(auth_client, producer):
    without = make_delegate(producer, ["farms.view_farm"], farm=FarmFactory(producer=producer))

    assert auth_client(without).get(URL).status_code == 403


def test_the_association_has_no_access(auth_client):
    assert auth_client(make_administrator()).get(URL).status_code == 403


def test_another_account_cannot_choose_the_producer(auth_client, owner, producer):
    other = PostharvestParametersFactory(slow_duration_day=9)

    response = auth_client(owner).get(URL, {"producer": other.producer_id})

    assert response.data["producer_id"] == str(producer.pk)
    assert response.data["is_default"] is True


class TestTechnicalAccount:
    @pytest.fixture
    def client(self, auth_client):
        return auth_client(UserFactory(is_superuser=True))

    def test_reads_the_producer_it_names(self, client):
        parameters = PostharvestParametersFactory(slow_duration_day=9)

        response = client.get(URL, {"producer": parameters.producer_id})

        assert response.status_code == 200
        assert response.data["producer_id"] == str(parameters.producer_id)
        assert response.data["values"]["slow_duration_day"] == 9

    def test_must_name_a_producer(self, client):
        response = client.get(URL)

        assert response.status_code == 400
        assert response.data["code"] == "validation_error"
        assert "producer" in response.data["fields"]

    def test_a_producer_that_does_not_exist_is_not_found(self, client):
        response = client.get(URL, {"producer": uuid.uuid4()})

        assert response.status_code == 404
        assert response.data["code"] == "not_found"
