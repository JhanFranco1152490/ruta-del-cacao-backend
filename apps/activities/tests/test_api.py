import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.inputs.tests.factories import AgriculturalInputFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

URL = "/api/agricultural-activities"
ALL_PERMISSIONS = [
    "farms.view_farm",
    "plots.view_plot",
    "activities.view_agriculturalactivity",
    "activities.add_agriculturalactivity",
    "activities.change_agriculturalactivity",
    "activities.complete_agriculturalactivity",
    "activities.delete_agriculturalactivity",
]


def in_days(days):
    return today_in_bogota() + timedelta(days=days)


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return UserFactory(
        producer=producer, first_name="Ana", last_name="Zapata", permissions=ALL_PERMISSIONS
    )


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def plot(producer):
    return PlotFactory(farm__producer=producer, code="P-03", farm__name="La Esperanza")


@pytest.fixture
def activity(plot, owner):
    return AgriculturalActivityFactory(plot=plot, assignee=owner, scheduled_date=in_days(5))


def body(plot, assignee, **overrides) -> dict:
    values = {
        "id": str(uuid.uuid4()),
        "plot_id": str(plot.pk),
        "activity_type": "fertilization",
        "scheduled_date": in_days(5).isoformat(),
        "assignee_id": str(assignee.pk),
    }
    values.update(overrides)
    return values


def detail(activity) -> str:
    return f"{URL}/{activity.pk}"


# --- Programar ----------------------------------------------------------------------------------


def test_it_schedules_and_answers_the_full_representation(client, plot, owner):
    sent = body(plot, owner)

    response = client.post(URL, sent, format="json")

    assert response.status_code == 201
    assert response["Location"] == f"{URL}/{sent['id']}"
    data = response.json()
    assert data["id"] == sent["id"]
    assert data["plot"] == {
        "id": str(plot.pk),
        "code": "P-03",
        "is_active": True,
        "farm": {"id": str(plot.farm_id), "name": "La Esperanza", "is_active": True},
    }
    assert data["producer_id"] == str(plot.farm.producer_id)
    assert data["activity_type"] == "fertilization"
    assert data["other_description"] is None
    assert data["status"] == "scheduled"
    assert data["state"] == "scheduled"
    assert data["days_late"] == 0
    assert data["assignee"] == {"id": str(owner.pk), "full_name": "Ana Zapata", "is_active": True}
    assert data["inputs"] == []
    assert data["done_date"] is None
    assert data["completed_by"] is None
    assert data["version"] == 1


def test_a_resend_answers_200_with_the_same_activity(client, plot, owner):
    sent = body(plot, owner)
    client.post(URL, sent, format="json")

    response = client.post(URL, sent, format="json")

    assert response.status_code == 200
    assert AgriculturalActivity.objects.count() == 1


def test_missing_fields_are_reported_by_field(client):
    response = client.post(URL, {}, format="json")

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert {"plot_id", "activity_type", "scheduled_date", "assignee_id"} <= set(
        response.json()["fields"]
    )


def test_an_unknown_field_is_rejected(client, plot, owner):
    response = client.post(URL, body(plot, owner, status="done"), format="json")

    assert response.status_code == 400
    assert "status" in response.json()["fields"]


def test_an_unknown_type_is_rejected(client, plot, owner):
    response = client.post(URL, body(plot, owner, activity_type="harvest"), format="json")

    assert response.status_code == 400
    assert "activity_type" in response.json()["fields"]


def test_a_past_date_is_a_validation_error(client, plot, owner):
    response = client.post(
        URL, body(plot, owner, scheduled_date=in_days(-1).isoformat()), format="json"
    )

    assert response.status_code == 400
    assert response.json()["fields"]["scheduled_date"] == ["La fecha debe ser actual o futura."]


def test_a_phytosanitary_control_is_422(client, plot, owner):
    response = client.post(
        URL, body(plot, owner, activity_type="phytosanitary_control"), format="json"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "activity_type_not_allowed"


def test_an_assignee_of_another_producer_is_422(client, plot):
    stranger = UserFactory(producer=ProducerFactory())

    response = client.post(URL, body(plot, stranger), format="json")

    assert response.status_code == 422
    assert response.json()["code"] == "assignee_not_available"


def test_a_plot_of_another_producer_is_404(client, owner):
    response = client.post(URL, body(PlotFactory(), owner), format="json")

    assert response.status_code == 404


# --- Consultar ----------------------------------------------------------------------------------


def test_the_detail_of_an_activity(client, activity):
    response = client.get(detail(activity))

    assert response.status_code == 200
    assert response.json()["id"] == str(activity.pk)


def test_a_delayed_activity_says_how_late_it_is(client, plot, owner):
    delayed = AgriculturalActivityFactory(plot=plot, assignee=owner, scheduled_date=in_days(-2))

    data = client.get(detail(delayed)).json()

    assert data["state"] == "delayed"
    assert data["days_late"] == 2


def test_an_activity_of_another_producer_is_404(client):
    response = client.get(detail(AgriculturalActivityFactory()))

    assert response.status_code == 404


# --- Editar -------------------------------------------------------------------------------------


def test_it_reschedules(client, activity):
    response = client.patch(
        detail(activity),
        {"scheduled_date": in_days(8).isoformat(), "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["scheduled_date"] == in_days(8).isoformat()
    assert response.json()["version"] == 2


def test_editing_needs_the_version(client, activity):
    response = client.patch(
        detail(activity), {"scheduled_date": in_days(8).isoformat()}, format="json"
    )

    assert response.status_code == 400
    assert "expected_version" in response.json()["fields"]


def test_the_plot_cannot_be_changed(client, activity):
    response = client.patch(
        detail(activity), {"plot_id": str(PlotFactory().pk), "expected_version": 1}, format="json"
    )

    assert response.status_code == 400
    assert "plot_id" in response.json()["fields"]


def test_an_old_version_answers_409_with_the_current_activity(client, activity):
    client.patch(
        detail(activity), {"activity_type": "irrigation", "expected_version": 1}, format="json"
    )

    response = client.patch(
        detail(activity), {"activity_type": "weed_control", "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_version"
    assert response.json()["current"]["activity_type"] == "irrigation"


def test_a_done_activity_is_409(client, plot, owner):
    done = AgriculturalActivityFactory(
        plot=plot,
        assignee=owner,
        status=ActivityStatus.DONE,
        done_date=today_in_bogota(),
        completed_at=timezone.now(),
    )

    response = client.patch(
        detail(done), {"activity_type": "irrigation", "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "activity_already_done"


def test_an_overdue_activity_is_409(client, plot, owner):
    overdue = AgriculturalActivityFactory(plot=plot, assignee=owner, scheduled_date=in_days(-3))

    response = client.patch(
        detail(overdue),
        {"scheduled_date": in_days(1).isoformat(), "expected_version": 1},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "activity_overdue"


# --- Eliminar -----------------------------------------------------------------------------------


def test_it_deletes_with_the_version_in_the_url(client, activity):
    response = client.delete(f"{detail(activity)}?expected_version=1")

    assert response.status_code == 204
    assert not AgriculturalActivity.objects.filter(pk=activity.pk).exists()


def test_deleting_needs_the_version(client, activity):
    response = client.delete(detail(activity))

    assert response.status_code == 400


# --- Registrar la realización -------------------------------------------------------------------


def completion_url(activity) -> str:
    return f"{detail(activity)}/completion"


def test_it_records_the_completion(client, activity, owner):
    response = client.post(
        completion_url(activity), {"done_date": today_in_bogota().isoformat()}, format="json"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == data["state"] == "done"
    assert data["done_date"] == today_in_bogota().isoformat()
    assert data["completed_by"] == {"id": str(owner.pk), "full_name": "Ana Zapata"}
    assert data["completed_at"] is not None


def test_a_resent_completion_answers_200(client, activity):
    sent = {"done_date": today_in_bogota().isoformat(), "inputs": []}
    client.post(completion_url(activity), sent, format="json")

    response = client.post(completion_url(activity), sent, format="json")

    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_a_future_completion_date_is_400(client, activity):
    response = client.post(
        completion_url(activity), {"done_date": in_days(1).isoformat()}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["fields"]["done_date"] == ["La fecha no puede ser futura."]


def test_an_unknown_input_is_400_so_the_queue_does_not_drop_it(client, activity):
    response = client.post(
        completion_url(activity),
        {
            "done_date": today_in_bogota().isoformat(),
            "inputs": [{"input_id": str(uuid.uuid4()), "quantity": "2"}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "inputs" in response.json()["fields"]


def test_a_quantity_with_more_than_three_decimals_is_400(client, activity, plot):
    item = AgriculturalInputFactory(producer=plot.farm.producer)

    response = client.post(
        completion_url(activity),
        {
            "done_date": today_in_bogota().isoformat(),
            "inputs": [{"input_id": str(item.pk), "quantity": "2.0005"}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "inputs" in response.json()["fields"]


def test_the_completion_with_inputs_shows_up_in_the_inventory(auth_client, client, activity, plot):
    item = AgriculturalInputFactory(producer=plot.farm.producer)

    response = client.post(
        completion_url(activity),
        {
            "done_date": today_in_bogota().isoformat(),
            "inputs": [{"input_id": str(item.pk), "quantity": "50"}],
        },
        format="json",
    )
    reader = UserFactory(
        producer=plot.farm.producer, permissions=["inputs.view_agriculturalinput"]
    )
    movements = auth_client(reader).get(
        "/api/input-movements", {"input": str(item.pk), "farm": str(plot.farm_id)}
    )

    assert response.status_code == 200
    [movement] = movements.json()["results"]
    assert movement["kind"] == "consumption"
    assert movement["quantity"] == "-50.000"
    assert movement["note"] == "Poda · P-03"


def test_an_inactive_input_is_422_with_its_id(client, activity, plot):
    item = AgriculturalInputFactory(producer=plot.farm.producer, is_active=False)

    response = client.post(
        completion_url(activity),
        {
            "done_date": today_in_bogota().isoformat(),
            "inputs": [{"input_id": str(item.pk), "quantity": "1"}],
        },
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "input_inactive"
    assert response.json()["input_ids"] == [str(item.pk)]


def test_a_monitoring_is_422(client, plot, owner):
    monitoring = AgriculturalActivityFactory(
        plot=plot, assignee=owner, activity_type=ActivityType.PHYTOSANITARY_MONITORING
    )

    response = client.post(
        completion_url(monitoring), {"done_date": today_in_bogota().isoformat()}, format="json"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "monitoring_requires_result"


# --- Responsables -------------------------------------------------------------------------------


def test_the_assignees_of_the_producer(client, owner, producer):
    UserFactory(producer=producer, first_name="Luis", last_name="Gómez", is_active=False)

    response = client.get(f"{URL}/assignees")

    assert response.status_code == 200
    assert response.json()["results"] == [
        {"id": response.json()["results"][0]["id"], "full_name": "Luis Gómez", "is_active": False},
        {"id": str(owner.pk), "full_name": "Ana Zapata", "is_active": True},
    ]


# --- Sesión y permisos --------------------------------------------------------------------------


def test_without_a_session_it_is_401(api_client, activity):
    assert api_client.get(detail(activity)).status_code == 401


@pytest.mark.parametrize(
    "method, path, permission",
    [
        ("get", "detail", "activities.view_agriculturalactivity"),
        ("post", "create", "activities.add_agriculturalactivity"),
        ("patch", "detail", "activities.change_agriculturalactivity"),
        ("post", "completion", "activities.complete_agriculturalactivity"),
        ("delete", "delete", "activities.delete_agriculturalactivity"),
        ("get", "assignees", "activities.view_agriculturalactivity"),
    ],
)
def test_each_action_needs_its_permission(
    auth_client, producer, activity, method, path, permission
):
    without = [code for code in ALL_PERMISSIONS if code != permission]
    employee = UserFactory(producer=producer, permissions=without)
    urls = {
        "detail": detail(activity),
        "create": URL,
        "completion": completion_url(activity),
        "delete": f"{detail(activity)}?expected_version=1",
        "assignees": f"{URL}/assignees",
    }

    response = getattr(auth_client(employee), method)(urls[path], {}, format="json")

    assert response.status_code == 403


def test_an_employee_with_the_delegated_permissions_schedules(auth_client, producer, plot, owner):
    employee = UserFactory(producer=producer, permissions=ALL_PERMISSIONS[:4])

    response = auth_client(employee).post(URL, body(plot, owner), format="json")

    assert response.status_code == 201


def test_an_account_without_activity_permissions_is_403(auth_client, activity):
    association = UserFactory(permissions=["farms.view_farm"])

    assert auth_client(association).get(detail(activity)).status_code == 403
