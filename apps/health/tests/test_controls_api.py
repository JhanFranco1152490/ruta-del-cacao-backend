import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.health.models import PhytosanitaryMonitoring, PhytosanitaryTreatment
from apps.health.tests.factories import PestDiseaseFactory
from apps.inputs.models import InputMovement
from apps.inputs.tests.factories import AgriculturalInputFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

COMPLETE = "activities.complete_agriculturalactivity"
SCHEDULE = "activities.add_agriculturalactivity"
VIEW = "activities.view_agriculturalactivity"


def days(offset):
    return today_in_bogota() + timedelta(days=offset)


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def plot(farm):
    return PlotFactory(farm=farm, code="P-03")


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


def planned_days_ago(activity, count=5):
    # El resultado no puede ser anterior al día en que se programó el monitoreo.
    AgriculturalActivity.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - timedelta(days=count)
    )
    activity.refresh_from_db()
    return activity


@pytest.fixture
def monitoring(plot, owner):
    return planned_days_ago(
        AgriculturalActivityFactory(
            plot=plot,
            activity_type=ActivityType.PHYTOSANITARY_MONITORING,
            scheduled_date=days(-2),
            assignee=owner,
        )
    )


@pytest.fixture
def monilia():
    return PestDiseaseFactory(name="Monilia")


@pytest.fixture
def product(producer):
    return AgriculturalInputFactory(producer=producer, name="Fungicida cúprico")


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


def monitoring_url(activity):
    return f"/api/agricultural-activities/{activity.pk}/monitoring"


def controls_url(detection_id):
    return f"/api/phytosanitary-detections/{detection_id}/controls"


def done_now(method="fruit_removal", inputs=(), control_id=None, **extra):
    return {
        "id": str(control_id or uuid.uuid4()),
        "mode": "done",
        "method": method,
        "method_description": None,
        "inputs": [{"input_id": str(item.pk), "quantity": quantity} for item, quantity in inputs],
        **extra,
    }


def for_later(assignee, on=None, control_id=None, **extra):
    return {
        "id": str(control_id or uuid.uuid4()),
        "mode": "scheduled",
        "scheduled_date": str(on or days(3)),
        "assignee_id": str(assignee.pk),
        "method": None,
        "planned_input_id": None,
        **extra,
    }


def result(pest, control=None, detection_id=None, done_on=None, affected=12):
    row = {
        "id": str(detection_id or uuid.uuid4()),
        "pest_disease_id": str(pest.pk),
        "affected_units": affected,
    }
    if control is not None:
        row["control"] = control
    return {
        "done_date": str(done_on or days(-1)),
        "sampling_unit": "trees",
        "evaluated_units": 50,
        "detections": [row],
    }


def control_of(detection_id) -> list[PhytosanitaryTreatment]:
    return list(
        PhytosanitaryTreatment.objects.filter(detection_id=detection_id).select_related("activity")
    )


def consumption(item):
    return list(
        InputMovement.objects.filter(input=item, kind=InputMovement.Kind.CONSUMPTION).values_list(
            "quantity", flat=True
        )
    )


def assert_nothing_saved(monitoring):
    monitoring.refresh_from_db()
    assert monitoring.status == ActivityStatus.SCHEDULED
    assert not PhytosanitaryMonitoring.objects.filter(activity=monitoring).exists()
    assert not AgriculturalActivity.objects.filter(
        activity_type=ActivityType.PHYTOSANITARY_CONTROL
    ).exists()
    assert not InputMovement.objects.filter(kind=InputMovement.Kind.CONSUMPTION).exists()


# --- En la planilla del monitoreo: "Lo hice en este momento" ------------------------------------


def test_done_now_creates_a_done_control_on_the_monitoring_date(
    client, monitoring, monilia, owner
):
    detection_id = uuid.uuid4()
    control_id = uuid.uuid4()

    response = client.post(
        monitoring_url(monitoring),
        result(monilia, done_now(control_id=control_id), detection_id=detection_id),
        format="json",
    )

    assert response.status_code == 201
    [treatment] = control_of(detection_id)
    control = treatment.activity
    assert control.pk == control_id
    assert control.activity_type == ActivityType.PHYTOSANITARY_CONTROL
    assert control.status == ActivityStatus.DONE
    assert control.done_date == days(-1)
    assert (control.assignee, control.completed_by) == (owner, owner)
    assert (treatment.method, treatment.method_description) == ("fruit_removal", None)


def test_done_now_discounts_the_inputs_it_used(client, monitoring, monilia, product):
    body = result(monilia, done_now(method="product_application", inputs=[(product, "0.5")]))

    response = client.post(monitoring_url(monitoring), body, format="json")

    assert response.status_code == 201
    assert consumption(product) == [Decimal("-0.500")]


def test_a_worker_who_only_records_can_do_it_now(auth_client, plot, farm, monilia):
    worker = make_delegate(farm.producer, [COMPLETE], farm=farm)
    own = planned_days_ago(
        AgriculturalActivityFactory(
            plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING, assignee=worker
        )
    )
    detection_id = uuid.uuid4()

    response = auth_client(worker).post(
        monitoring_url(own), result(monilia, done_now(), detection_id=detection_id), format="json"
    )

    assert response.status_code == 201
    assert control_of(detection_id)[0].activity.assignee == worker


def test_the_technical_account_leaves_the_monitoring_assignee(
    auth_client, monitoring, monilia, owner
):
    detection_id = uuid.uuid4()
    technical = UserFactory(is_superuser=True)

    response = auth_client(technical).post(
        monitoring_url(monitoring),
        result(monilia, done_now(), detection_id=detection_id),
        format="json",
    )

    assert response.status_code == 201
    control = control_of(detection_id)[0].activity
    assert (control.assignee, control.completed_by) == (owner, technical)


@pytest.mark.parametrize(
    "control, field",
    [
        (lambda: done_now(method=None), "method"),
        (lambda: done_now(method="other"), "method_description"),
        (lambda: done_now(method="other", method_description="   "), "method_description"),
        (
            lambda: done_now(method="fruit_removal", method_description="Quité mazorcas"),
            "method_description",
        ),
        (lambda: done_now(method="product_application"), "inputs"),
    ],
)
def test_done_now_says_what_was_done(client, monitoring, monilia, control, field):
    response = client.post(monitoring_url(monitoring), result(monilia, control()), format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]
    assert_nothing_saved(monitoring)


def test_other_is_saved_with_what_was_done(client, monitoring, monilia):
    detection_id = uuid.uuid4()
    control = done_now(method="other", method_description="  Trampa con melaza ")

    response = client.post(
        monitoring_url(monitoring),
        result(monilia, control, detection_id=detection_id),
        format="json",
    )

    assert response.status_code == 201
    assert control_of(detection_id)[0].method_description == "Trampa con melaza"


# --- En la planilla del monitoreo: "Programarlo para después" -----------------------------------


def test_for_later_schedules_a_control_in_the_calendar(client, monitoring, monilia, product):
    foreman = foreman_of(monitoring.plot.farm)
    detection_id = uuid.uuid4()
    control = for_later(foreman, on=days(3), method="product_application")
    control["planned_input_id"] = str(product.pk)

    response = client.post(
        monitoring_url(monitoring),
        result(monilia, control, detection_id=detection_id),
        format="json",
    )

    assert response.status_code == 201
    [treatment] = control_of(detection_id)
    assert treatment.activity.status == ActivityStatus.SCHEDULED
    assert (treatment.activity.scheduled_date, treatment.activity.assignee) == (days(3), foreman)
    assert (treatment.method, treatment.planned_input) == ("product_application", product)
    # El insumo previsto es solo una referencia: no se descuenta.
    assert consumption(product) == []


def test_a_worker_who_does_not_schedule_cannot_leave_it_for_later(
    auth_client, plot, farm, monilia, owner
):
    worker = make_delegate(farm.producer, [COMPLETE], farm=farm)
    own = planned_days_ago(
        AgriculturalActivityFactory(
            plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING, assignee=worker
        )
    )

    response = auth_client(worker).post(
        monitoring_url(own), result(monilia, for_later(owner)), format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert_nothing_saved(own)


def test_an_invalid_control_leaves_nothing_saved(client, monitoring, product, owner):
    # El primer control es válido y descuenta; el segundo no: no queda ni el monitoreo, ni el
    # primer control, ni su salida del inventario.
    stranger = make_producer_owner(ProducerFactory())
    body = result(PestDiseaseFactory(), done_now("product_application", [(product, "1")]))
    body["detections"].append(
        {
            "id": str(uuid.uuid4()),
            "pest_disease_id": str(PestDiseaseFactory().pk),
            "affected_units": 3,
            "control": for_later(stranger),
        }
    )

    response = client.post(monitoring_url(monitoring), body, format="json")

    assert response.status_code == 422
    assert response.data["code"] == "assignee_not_available"
    assert_nothing_saved(monitoring)


def test_mode_fields_do_not_mix(client, monitoring, monilia, owner, product):
    with_inputs = for_later(owner, inputs=[{"input_id": str(product.pk), "quantity": "1"}])

    response = client.post(monitoring_url(monitoring), result(monilia, with_inputs), format="json")

    assert response.status_code == 400
    assert_nothing_saved(monitoring)


def test_a_control_is_optional(client, monitoring, monilia):
    detection_id = uuid.uuid4()

    response = client.post(
        monitoring_url(monitoring), result(monilia, detection_id=detection_id), format="json"
    )

    assert response.status_code == 201
    assert control_of(detection_id) == []


def test_resending_the_monitoring_with_its_controls_changes_nothing(
    client, monitoring, monilia, product, owner
):
    body = result(monilia, done_now("product_application", [(product, "2")]))
    client.post(monitoring_url(monitoring), body, format="json")

    response = client.post(monitoring_url(monitoring), body, format="json")

    assert response.status_code == 200
    assert PhytosanitaryTreatment.objects.count() == 1
    assert consumption(product) == [Decimal("-2.000")]


def test_resending_with_another_control_is_a_409(client, monitoring, monilia):
    body = result(monilia, done_now())
    client.post(monitoring_url(monitoring), body, format="json")
    body["detections"][0]["control"]["method"] = "sanitary_pruning"

    response = client.post(monitoring_url(monitoring), body, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "activity_already_done"


# --- Desde una detección ------------------------------------------------------------------------


@pytest.fixture
def detection_id(client, monitoring, monilia):
    detection_id = uuid.uuid4()
    response = client.post(
        monitoring_url(monitoring), result(monilia, detection_id=detection_id), format="json"
    )
    assert response.status_code == 201
    return detection_id


def scheduled_body(assignee, **extra):
    return {**for_later(assignee), **extra}


def done_body(assignee, done_on=None, **extra):
    return {
        **done_now(**extra),
        "done_date": str(done_on or today_in_bogota()),
        "assignee_id": str(assignee.pk),
        "captured_at": None,
    }


def test_a_control_is_scheduled_from_a_detection(client, detection_id, owner):
    body = scheduled_body(owner)

    response = client.post(controls_url(detection_id), body, format="json")

    assert response.status_code == 201
    assert response.data["id"] == body["id"]
    assert response.data["activity_type"] == ActivityType.PHYTOSANITARY_CONTROL
    assert response.data["state"] == "scheduled"
    assert [t.activity_id for t in control_of(detection_id)] == [uuid.UUID(body["id"])]


def test_a_done_control_is_recorded_from_a_detection(client, detection_id, owner, product):
    body = done_body(owner, method="product_application", inputs=[(product, "2.5")])

    response = client.post(controls_url(detection_id), body, format="json")

    assert response.status_code == 201
    assert response.data["status"] == ActivityStatus.DONE
    assert consumption(product) == [Decimal("-2.500")]


@pytest.mark.parametrize("offset", [1, -2])
def test_a_done_control_is_neither_future_nor_before_the_monitoring(
    client, detection_id, owner, offset
):
    # El monitoreo se registró ayer.
    response = client.post(
        controls_url(detection_id), done_body(owner, done_on=days(offset)), format="json"
    )

    assert response.status_code == 400
    assert "done_date" in response.data["fields"]
    assert control_of(detection_id) == []


def test_a_detection_can_have_several_controls(client, detection_id, owner):
    client.post(controls_url(detection_id), done_body(owner), format="json")

    response = client.post(controls_url(detection_id), scheduled_body(owner), format="json")

    assert response.status_code == 201
    assert len(control_of(detection_id)) == 2


def test_the_same_control_sent_again_is_a_200(client, detection_id, owner):
    body = scheduled_body(owner)
    client.post(controls_url(detection_id), body, format="json")

    response = client.post(controls_url(detection_id), body, format="json")

    assert response.status_code == 200
    assert len(control_of(detection_id)) == 1


def test_the_same_id_with_other_content_is_a_400_on_the_id(client, detection_id, owner):
    body = scheduled_body(owner)
    client.post(controls_url(detection_id), body, format="json")

    response = client.post(
        controls_url(detection_id), {**body, "scheduled_date": str(days(5))}, format="json"
    )

    assert response.status_code == 400
    assert "id" in response.data["fields"]


def test_an_id_used_by_another_activity_is_a_400_on_the_id(client, detection_id, owner, plot):
    taken = AgriculturalActivityFactory(plot=plot)

    response = client.post(
        controls_url(detection_id), scheduled_body(owner, id=str(taken.pk)), format="json"
    )

    assert response.status_code == 400
    assert "id" in response.data["fields"]


def test_an_inactive_planned_input_is_a_422(client, detection_id, owner, product):
    product.is_active = False
    product.save()

    response = client.post(
        controls_url(detection_id),
        scheduled_body(owner, planned_input_id=str(product.pk)),
        format="json",
    )

    assert response.status_code == 422
    assert response.data["code"] == "input_inactive"


def test_a_planned_input_of_another_producer_is_a_400(client, detection_id, owner):
    foreign = AgriculturalInputFactory()

    response = client.post(
        controls_url(detection_id),
        scheduled_body(owner, planned_input_id=str(foreign.pk)),
        format="json",
    )

    assert response.status_code == 400
    assert "planned_input_id" in response.data["fields"]


def test_the_foreman_schedules_and_records_controls(auth_client, detection_id, farm, owner):
    foreman = foreman_of(farm)
    client = auth_client(foreman)

    # Un empleado no le asigna labores al Productor: se asigna el control a sí mismo.
    scheduled = client.post(controls_url(detection_id), scheduled_body(foreman), format="json")
    done = client.post(controls_url(detection_id), done_body(foreman), format="json")

    assert (scheduled.status_code, done.status_code) == (201, 201)


def test_a_worker_who_only_records_cannot_create_controls(auth_client, detection_id, farm, owner):
    client = auth_client(make_delegate(farm.producer, [COMPLETE, VIEW], farm=farm))

    scheduled = client.post(controls_url(detection_id), scheduled_body(owner), format="json")
    done = client.post(controls_url(detection_id), done_body(owner), format="json")

    assert (scheduled.status_code, done.status_code) == (403, 403)


def test_scheduling_without_recording_cannot_create_a_done_control(
    auth_client, detection_id, farm, owner
):
    planner = make_delegate(farm.producer, [SCHEDULE, VIEW], farm=farm)
    worker = make_delegate(farm.producer, [COMPLETE], farm=farm)
    client = auth_client(planner)

    scheduled = client.post(controls_url(detection_id), scheduled_body(worker), format="json")
    done = client.post(controls_url(detection_id), done_body(worker), format="json")

    assert (scheduled.status_code, done.status_code) == (201, 403)


def test_a_detection_of_another_farm_is_a_404(auth_client, detection_id, farm, owner):
    other_foreman = foreman_of(FarmFactory(producer=farm.producer))

    response = auth_client(other_foreman).post(
        controls_url(detection_id), scheduled_body(owner), format="json"
    )

    assert response.status_code == 404


def test_a_detection_of_another_producer_is_a_404(auth_client, detection_id, owner):
    stranger = make_producer_owner(ProducerFactory())

    response = auth_client(stranger).post(
        controls_url(detection_id), scheduled_body(owner), format="json"
    )

    assert response.status_code == 404


def test_a_monitoring_without_presence_offers_no_detection_to_control(client, monitoring, owner):
    # Sin presencia no hay detecciones: no existe ninguna a la que pedirle un control.
    client.post(
        monitoring_url(monitoring),
        {
            "done_date": str(days(-1)),
            "sampling_unit": "trees",
            "evaluated_units": 50,
            "no_presence": True,
        },
        format="json",
    )

    response = client.post(controls_url(uuid.uuid4()), scheduled_body(owner), format="json")

    assert response.status_code == 404
