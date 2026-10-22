from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.common.contracts.postharvest_parameters import drying_parameters
from apps.farms.tests.factories import FarmFactory
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.models import (
    PostharvestParameters,
    PostharvestParametersAuditEvent,
)
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestParametersFactory
from .test_api_read import BASELINE_VALUES

pytestmark = pytest.mark.django_db

URL = "/api/postharvest-parameters"
RESET_URL = f"{URL}/reset"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def customized(producer):
    return PostharvestParametersFactory(
        producer=producer, slow_duration_day=9, overdried_moisture_pct=Decimal("5.5")
    )


def test_resetting_brings_back_the_baseline(client, producer, customized):
    response = client.post(RESET_URL, {"expected_version": 1}, format="json")

    assert response.status_code == 200
    assert response.data["is_default"] is True
    assert response.data["version"] == 0
    assert response.data["values"] == BASELINE_VALUES
    assert not PostharvestParameters.objects.filter(pk=producer.pk).exists()
    assert drying_parameters(producer.pk) == DRYING_BASELINE


def test_resetting_records_the_values_that_were_there(client, owner, producer, customized):
    client.post(RESET_URL, {"expected_version": 1}, format="json")

    event = PostharvestParametersAuditEvent.objects.get(producer=producer)
    assert event.action == "reset"
    assert event.actor == owner
    assert event.version == 0
    assert event.changes == {
        "overdried_moisture_pct": {"before": "5.5", "after": "6.0"},
        "slow_duration_day": {"before": 9, "after": 8},
    }


def test_resetting_the_baseline_records_nothing(client):
    response = client.post(RESET_URL, {"expected_version": 0}, format="json")

    assert response.status_code == 200
    assert response.data["is_default"] is True
    assert not PostharvestParametersAuditEvent.objects.exists()


def test_a_stale_version_is_rejected_and_nothing_is_reset(client, producer, customized):
    response = client.post(RESET_URL, {"expected_version": 0}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["values"]["slow_duration_day"] == 9
    assert drying_parameters(producer.pk).slow_duration_day == 9


def test_the_expected_version_is_required(client, customized):
    response = client.post(RESET_URL, {}, format="json")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_the_next_save_starts_again_at_version_one(client, producer, customized):
    client.post(RESET_URL, {"expected_version": 1}, format="json")

    response = client.put(
        URL,
        {"expected_version": 0, "values": {**BASELINE_VALUES, "accelerated_day": 2}},
        format="json",
    )

    assert response.data["version"] == 1
    assert drying_parameters(producer.pk).accelerated_day == 2


def test_the_foreman_cannot_reset(auth_client, producer, customized):
    foreman = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)),
        get_system_role(FOREMAN),
    )

    response = auth_client(foreman).post(RESET_URL, {"expected_version": 1}, format="json")

    assert response.status_code == 403
    assert PostharvestParameters.objects.filter(pk=producer.pk).exists()


def test_the_technical_account_resets_the_producer_it_names(auth_client, producer, customized):
    technical = UserFactory(is_superuser=True)

    response = auth_client(technical).post(
        RESET_URL, {"expected_version": 1, "producer": str(producer.pk)}, format="json"
    )

    assert response.status_code == 200
    assert drying_parameters(producer.pk) == DRYING_BASELINE
