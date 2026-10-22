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
from apps.common.contracts.postharvest_parameters import drying_parameters
from apps.farms.tests.factories import FarmFactory
from apps.postharvest_parameters.models import (
    PostharvestParameters,
    PostharvestParametersAuditEvent,
)
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestParametersFactory
from .test_api_read import BASELINE_VALUES

pytestmark = pytest.mark.django_db

URL = "/api/postharvest-parameters"
CHANGE = "postharvest_parameters.change_postharvestparameters"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


def body(expected_version=0, **changes):
    return {"expected_version": expected_version, "values": {**BASELINE_VALUES, **changes}}


def field_errors(response, name):
    assert response.status_code == 400, response.data
    assert response.data["code"] == "validation_error"
    return response.data["fields"][name]


# --- Guardar ---


def test_the_first_save_creates_the_parameters(client, owner, producer):
    response = client.put(URL, body(slow_duration_day=9), format="json")

    assert response.status_code == 200
    assert response.data["is_default"] is False
    assert response.data["version"] == 1
    assert response.data["values"]["slow_duration_day"] == 9
    assert response.data["updated_by"]["id"] == str(owner.pk)
    assert drying_parameters(producer.pk).slow_duration_day == 9


def test_the_first_save_records_what_changed_from_the_baseline(client, owner, producer):
    client.put(URL, body(slow_duration_day=9, overdried_moisture_pct="5.5"), format="json")

    event = PostharvestParametersAuditEvent.objects.get(producer=producer)
    assert event.action == "updated"
    assert event.actor == owner
    assert event.version == 1
    assert event.changes == {
        "overdried_moisture_pct": {"before": "6.0", "after": "5.5"},
        "slow_duration_day": {"before": 8, "after": 9},
    }


def test_saving_the_baseline_values_keeps_them_as_the_producer_s_own(client, producer):
    response = client.put(URL, body(), format="json")

    assert response.status_code == 200
    assert response.data["is_default"] is False
    assert PostharvestParameters.objects.filter(pk=producer.pk).exists()


def test_a_later_save_raises_the_version_and_records_only_the_changes(client, producer):
    PostharvestParametersFactory(producer=producer, slow_duration_day=9)

    response = client.put(URL, body(1, slow_duration_day=9, accelerated_day=2), format="json")

    assert response.data["version"] == 2
    event = PostharvestParametersAuditEvent.objects.get(producer=producer)
    assert event.changes == {"accelerated_day": {"before": 3, "after": 2}}


def test_a_save_without_real_changes_leaves_everything_as_it_was(client, producer):
    PostharvestParametersFactory(producer=producer, slow_duration_day=9)

    response = client.put(URL, body(1, slow_duration_day=9), format="json")

    assert response.status_code == 200
    assert response.data["version"] == 1
    assert not PostharvestParametersAuditEvent.objects.exists()


def test_a_stale_version_is_rejected_with_the_current_parameters(client, producer):
    PostharvestParametersFactory(producer=producer, slow_duration_day=9)

    response = client.put(URL, body(0, accelerated_day=2), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 1
    assert response.data["current"]["values"]["slow_duration_day"] == 9
    assert drying_parameters(producer.pk).accelerated_day == 3


def test_a_percentage_can_also_be_sent_as_a_number(client):
    response = client.put(URL, body(overdried_moisture_pct=5.5), format="json")

    assert response.data["values"]["overdried_moisture_pct"] == "5.5"


# --- Validaciones ---


@pytest.mark.parametrize("value", ["100.0", "0.0"])
def test_a_percentage_at_its_edges_is_accepted(client, value):
    response = client.put(URL, body(accelerated_moisture_pct=value), format="json")

    assert response.status_code == 200


@pytest.mark.parametrize("value", ["100.1", "-0.1", "1000.0"])
def test_a_percentage_out_of_range_is_rejected(client, value):
    errors = field_errors(
        client.put(URL, body(accelerated_moisture_pct=value), format="json"),
        "accelerated_moisture_pct",
    )

    assert errors == ["Debe estar entre 0 % y 100 %."]


def test_a_percentage_with_two_decimals_is_rejected(client):
    response = client.put(URL, body(overdried_moisture_pct="5.55"), format="json")

    assert field_errors(response, "overdried_moisture_pct") == ["Usa máximo 1 decimal."]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("slow_duration_day", 0, "Debe ser un número entero mayor que cero."),
        ("estimated_days_max", 61, "Revisa la cifra: un secado no pasa de 60 días."),
        ("slow_stall_window_hours", 0, "Debe ser un número entero mayor que cero."),
        ("slow_stall_window_hours", 241, "Revisa la cifra: la ventana no pasa de 240 horas."),
        ("accelerated_day", "2.5", "Debe ser un número entero mayor que cero."),
    ],
)
def test_days_and_hours_must_be_positive_whole_numbers_within_their_cap(
    client, field, value, message
):
    assert field_errors(client.put(URL, body(**{field: value}), format="json"), field) == [message]


@pytest.mark.parametrize(
    ("field", "value"), [("estimated_days_max", 60), ("slow_stall_window_hours", 240)]
)
def test_the_caps_themselves_are_accepted(client, field, value):
    changes = {field: value}
    if field == "estimated_days_max":
        changes["estimated_days_min"] = 5

    assert client.put(URL, body(**changes), format="json").status_code == 200


def test_the_stall_drop_must_be_above_zero(client):
    response = client.put(URL, body(slow_stall_min_drop_pct="0.0"), format="json")

    assert field_errors(response, "slow_stall_min_drop_pct") == ["Debe ser mayor que cero."]


@pytest.mark.parametrize(
    ("low", "high", "low_value", "high_value"),
    [
        ("entry_moisture_min_pct", "entry_moisture_max_pct", "62.0", "60.0"),
        ("target_moisture_min_pct", "target_moisture_max_pct", "7.6", "7.5"),
        ("estimated_days_min", "estimated_days_max", 8, 7),
        ("near_target_min_pct", "near_target_max_pct", "8.6", "8.5"),
    ],
)
def test_a_minimum_above_its_maximum_is_marked_on_the_minimum(
    client, producer, low, high, low_value, high_value
):
    response = client.put(URL, body(**{low: low_value, high: high_value}), format="json")

    assert field_errors(response, low) == ["El mínimo no puede ser mayor que el máximo"]
    assert high not in response.data["fields"]
    assert not PostharvestParameters.objects.filter(pk=producer.pk).exists()


def test_a_minimum_equal_to_its_maximum_is_accepted(client):
    response = client.put(
        URL, body(entry_moisture_min_pct="58.0", entry_moisture_max_pct="58.0"), format="json"
    )

    assert response.status_code == 200


def test_every_parameter_is_required(client):
    values = dict(BASELINE_VALUES)
    del values["overdried_moisture_pct"]

    response = client.put(URL, {"expected_version": 0, "values": values}, format="json")

    assert field_errors(response, "overdried_moisture_pct")


def test_an_unknown_parameter_is_rejected(client):
    response = client.put(URL, body(fermentation_temperature="45.0"), format="json")

    assert field_errors(response, "fermentation_temperature") == ["Campo no permitido."]


def test_the_expected_version_is_required(client):
    response = client.put(URL, {"values": BASELINE_VALUES}, format="json")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


# --- Quién guarda ---


def test_saving_needs_a_session(anonymous_client):
    assert anonymous_client.put(URL, body(), format="json").status_code == 401


def test_the_foreman_reads_but_does_not_change_them(auth_client, producer):
    foreman = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)),
        get_system_role(FOREMAN),
    )

    response = auth_client(foreman).put(URL, body(slow_duration_day=9), format="json")

    assert response.status_code == 403
    assert not PostharvestParameters.objects.exists()


def test_a_custom_role_with_the_permission_saves(auth_client, producer):
    delegate = make_delegate(producer, [CHANGE])

    response = auth_client(delegate).put(URL, body(slow_duration_day=9), format="json")

    assert response.status_code == 200
    assert drying_parameters(producer.pk).slow_duration_day == 9


def test_the_association_cannot_save(auth_client):
    response = auth_client(make_administrator()).put(URL, body(), format="json")

    assert response.status_code == 403


def test_another_account_saves_only_its_own_producer(client, producer):
    other = ProducerFactory()

    response = client.put(
        URL, {**body(slow_duration_day=9), "producer": str(other.pk)}, format="json"
    )

    assert response.data["producer_id"] == str(producer.pk)
    assert drying_parameters(other.pk).slow_duration_day == 8


class TestTechnicalAccount:
    @pytest.fixture
    def technical(self):
        return UserFactory(is_superuser=True)

    def test_saves_the_parameters_of_the_producer_it_names(self, auth_client, technical):
        producer = ProducerFactory()

        response = auth_client(technical).put(
            URL, {**body(slow_duration_day=9), "producer": str(producer.pk)}, format="json"
        )

        assert response.status_code == 200
        assert drying_parameters(producer.pk).slow_duration_day == 9
        event = PostharvestParametersAuditEvent.objects.get(producer=producer)
        assert event.actor == technical

    def test_must_name_a_producer(self, auth_client, technical):
        response = auth_client(technical).put(URL, body(), format="json")

        assert response.status_code == 400
        assert "producer" in response.data["fields"]


def test_the_values_are_kept_exactly_as_sent(client, producer):
    client.put(URL, body(near_target_min_pct="7.8", near_target_max_pct="8.4"), format="json")

    stored = PostharvestParameters.objects.get(pk=producer.pk)
    assert stored.near_target_min_pct == Decimal("7.8")
    assert stored.near_target_max_pct == Decimal("8.4")
