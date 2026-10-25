from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.postharvest_parameters.fields import FIELDS
from apps.postharvest_parameters.models import (
    PostharvestParameters,
    PostharvestParametersAuditEvent,
)

from .factories import PostharvestParametersFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]

CHANGELIST = "admin:postharvest_parameters_postharvestparameters_changelist"


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def client(superuser):
    return login(superuser)


def change_url(parameters):
    return reverse(
        "admin:postharvest_parameters_postharvestparameters_change", args=[parameters.pk]
    )


def form(parameters, **overrides):
    data = {name: getattr(parameters, name) for name in FIELDS}
    data["expected_version"] = parameters.version
    data.update(overrides)
    return data


def test_the_list_and_the_record_open(client):
    parameters = PostharvestParametersFactory()

    assert client.get(reverse(CHANGELIST)).status_code == 200
    assert client.get(change_url(parameters)).status_code == 200


def test_parameters_are_not_added_from_the_admin(client):
    # Un productor sin parámetros ya usa la línea base.
    add = reverse("admin:postharvest_parameters_postharvestparameters_add")

    assert client.get(add).status_code == 403


def test_saving_goes_through_the_service_and_the_history_names_the_admin(client, superuser):
    parameters = PostharvestParametersFactory()

    response = client.post(change_url(parameters), form(parameters, slow_duration_day=9))

    assert response.status_code == 302
    parameters.refresh_from_db()
    assert (parameters.slow_duration_day, parameters.version) == (9, 2)
    event = PostharvestParametersAuditEvent.objects.get(producer=parameters.producer)
    assert event.actor == superuser
    assert event.changes == {"slow_duration_day": {"before": 8, "after": 9}}


def test_a_minimum_above_its_maximum_is_refused_with_the_api_message(client):
    parameters = PostharvestParametersFactory()

    response = client.post(
        change_url(parameters), form(parameters, estimated_days_min=8, estimated_days_max=7)
    )

    assert "El mínimo no puede ser mayor que el máximo" in response.content.decode()
    parameters.refresh_from_db()
    assert (parameters.estimated_days_min, parameters.version) == (5, 1)


def test_a_value_out_of_its_cap_is_refused_with_the_api_message(client):
    parameters = PostharvestParametersFactory()

    response = client.post(change_url(parameters), form(parameters, slow_stall_window_hours=480))

    assert "la ventana no pasa de 240 horas" in response.content.decode()
    parameters.refresh_from_db()
    assert parameters.slow_stall_window_hours == 48


def test_a_stale_form_is_rejected_and_changes_nothing(client):
    parameters = PostharvestParametersFactory()
    stale = form(parameters, slow_duration_day=9)
    PostharvestParameters.objects.filter(pk=parameters.pk).update(version=2)

    response = client.post(change_url(parameters), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    parameters.refresh_from_db()
    assert parameters.slow_duration_day == 8


def test_resetting_from_the_list_goes_through_the_service(client, superuser):
    parameters = PostharvestParametersFactory(overdried_moisture_pct=Decimal("5.5"))
    other = PostharvestParametersFactory()

    response = client.post(
        reverse(CHANGELIST),
        {"action": "reset_to_baseline", "_selected_action": [str(parameters.pk)]},
    )

    assert response.status_code == 302
    assert not PostharvestParameters.objects.filter(pk=parameters.pk).exists()
    assert PostharvestParameters.objects.filter(pk=other.pk).exists()
    event = PostharvestParametersAuditEvent.objects.get(producer=parameters.producer)
    assert (event.action, event.actor) == ("reset", superuser)


def test_the_parameters_are_not_deleted_one_by_one(client):
    parameters = PostharvestParametersFactory()
    delete = reverse(
        "admin:postharvest_parameters_postharvestparameters_delete", args=[parameters.pk]
    )

    assert client.get(delete).status_code == 403


def test_the_history_is_read_only(client):
    parameters = PostharvestParametersFactory()
    event = PostharvestParametersAuditEvent.objects.create(
        producer=parameters.producer, action="updated", version=1
    )
    url = reverse(
        "admin:postharvest_parameters_postharvestparametersauditevent_change", args=[event.pk]
    )

    response = client.post(url, {"action": "reset", "version": 0})

    event.refresh_from_db()
    assert event.action == "updated"
    assert response.status_code == 403
