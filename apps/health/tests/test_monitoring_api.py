import uuid
from datetime import timedelta
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
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.health.models import Detection, PestDisease, PhytosanitaryMonitoring
from apps.health.tests.factories import DetectionFactory, PestDiseaseFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

COMPLETE = "activities.complete_agriculturalactivity"
SCHEDULE = "activities.add_agriculturalactivity"


def url(activity) -> str:
    return f"/api/agricultural-activities/{activity.pk}/monitoring"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def plot(producer):
    return PlotFactory(farm=FarmFactory(producer=producer), code="P-03")


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def monitoring(plot, owner):
    return AgriculturalActivityFactory(
        plot=plot,
        activity_type=ActivityType.PHYTOSANITARY_MONITORING,
        scheduled_date=today_in_bogota(),
        assignee=owner,
    )


@pytest.fixture
def monilia():
    return PestDiseaseFactory(name="Monilia", kind="disease")


@pytest.fixture
def trips():
    return PestDiseaseFactory(name="Trips")


def detection(pest=None, affected=12, other=None, detection_id=None):
    return {
        "id": str(detection_id or uuid.uuid4()),
        "pest_disease_id": str(pest.pk) if pest is not None else None,
        "other_description": other,
        "affected_units": affected,
    }


def result(*detections, **overrides):
    return {
        "done_date": str(today_in_bogota()),
        "sampling_unit": "trees",
        "evaluated_units": 50,
        "sampling_method": "zigzag",
        "notes": "Foco de infección en la zona baja.",
        "no_presence": False,
        "detections": list(detections),
        "captured_at": "2026-10-19T15:20:00Z",
        **overrides,
    }


def stored(activity) -> PhytosanitaryMonitoring:
    return PhytosanitaryMonitoring.objects.get(activity=activity)


# --- Registrar ----------------------------------------------------------------------------------


def test_the_result_is_recorded_and_the_monitoring_is_done(client, monitoring, monilia, owner):
    detection_id = uuid.uuid4()

    response = client.post(
        url(monitoring), result(detection(monilia, 12, detection_id=detection_id)), format="json"
    )

    assert response.status_code == 201
    assert response.data["id"] == str(monitoring.pk)
    assert response.data["status"] == ActivityStatus.DONE
    assert response.data["completed_by"]["id"] == owner.pk
    monitoring.refresh_from_db()
    assert monitoring.done_date == today_in_bogota()
    saved = stored(monitoring)
    assert (saved.sampling_unit, saved.evaluated_units) == ("trees", 50)
    assert (saved.sampling_method, saved.notes) == ("zigzag", "Foco de infección en la zona baja.")
    row = saved.detections.get()
    assert (row.pk, row.pest_disease, row.affected_units) == (detection_id, monilia, 12)
    assert row.incidence == Decimal("24.00")


def test_without_presence_it_is_done_without_detections(client, monitoring):
    response = client.post(url(monitoring), result(no_presence=True), format="json")

    assert response.status_code == 201
    saved = stored(monitoring)
    assert saved.no_presence is True
    assert not saved.detections.exists()


def test_pods_and_optional_fields(client, monitoring, monilia):
    body = result(detection(monilia, 3), sampling_unit="pods", sampling_method=None, notes="   ")

    response = client.post(url(monitoring), body, format="json")

    assert response.status_code == 201
    saved = stored(monitoring)
    assert (saved.sampling_unit, saved.sampling_method, saved.notes) == ("pods", None, None)


def test_other_is_saved_with_its_text_and_the_catalog_does_not_change(client, monitoring):
    body = result(detection(other="  Hormigas en las hojas ", affected=3))

    response = client.post(url(monitoring), body, format="json")

    assert response.status_code == 201
    row = stored(monitoring).detections.get()
    assert (row.pest_disease, row.other_description) == (None, "Hormigas en las hojas")
    assert row.normalized_other == "hormigasenlashojas"
    assert row.incidence == Decimal("6.00")
    assert not PestDisease.objects.exists()


@pytest.mark.parametrize(
    "affected, evaluated, incidence",
    [
        (1, 3, "33.33"),
        (2, 3, "66.67"),
        (50, 50, "100.00"),
        # 0,125 %: redondea hacia arriba, no al par.
        (1, 800, "0.13"),
    ],
)
def test_the_incidence_is_rounded_half_up(
    client, monitoring, monilia, affected, evaluated, incidence
):
    body = result(detection(monilia, affected), evaluated_units=evaluated)

    response = client.post(url(monitoring), body, format="json")

    assert response.status_code == 201
    assert stored(monitoring).detections.get().incidence == Decimal(incidence)


def test_an_inactive_plot_or_farm_does_not_block_the_result(client, monitoring, monilia, plot):
    plot.is_active = False
    plot.save()
    plot.farm.is_active = False
    plot.farm.save()

    response = client.post(url(monitoring), result(detection(monilia)), format="json")

    assert response.status_code == 201


# --- Validaciones -------------------------------------------------------------------------------


def assert_rejected(response, field, status_code=400):
    assert response.status_code == status_code, response.data
    assert field in response.data["fields"], response.data


def assert_nothing_saved(monitoring):
    monitoring.refresh_from_db()
    assert monitoring.status == ActivityStatus.SCHEDULED
    assert not PhytosanitaryMonitoring.objects.filter(activity=monitoring).exists()
    assert not Detection.objects.filter(monitoring__activity=monitoring).exists()


@pytest.mark.parametrize("evaluated", [0, -5])
def test_the_evaluated_units_are_more_than_zero(client, monitoring, monilia, evaluated):
    body = result(detection(monilia), evaluated_units=evaluated)

    assert_rejected(client.post(url(monitoring), body, format="json"), "evaluated_units")
    assert_nothing_saved(monitoring)


def test_the_evaluated_units_cannot_overflow_the_column(client, monitoring, monilia):
    body = result(detection(monilia), evaluated_units=10_000_000_000)

    assert_rejected(client.post(url(monitoring), body, format="json"), "evaluated_units")
    assert_nothing_saved(monitoring)


def test_the_affected_units_cannot_overflow_the_column(client, monitoring, monilia):
    body = result(detection(monilia, 10_000_000_000), evaluated_units=10_000_000_000)

    response = client.post(url(monitoring), body, format="json")

    assert response.status_code == 400, response.data
    assert_nothing_saved(monitoring)


@pytest.mark.parametrize("affected", [0, -1])
def test_the_affected_units_are_more_than_zero(client, monitoring, monilia, affected):
    body = result(detection(monilia, affected))

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_the_affected_units_cannot_exceed_the_evaluated(client, monitoring, monilia):
    body = result(detection(monilia, 51), evaluated_units=50)

    response = client.post(url(monitoring), body, format="json")

    assert_rejected(response, "detections")
    assert "(50)" in str(response.data["fields"]["detections"])
    assert_nothing_saved(monitoring)


def test_without_presence_unchecked_it_needs_a_detection(client, monitoring):
    assert_rejected(client.post(url(monitoring), result(), format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_without_presence_it_cannot_bring_detections(client, monitoring, monilia):
    body = result(detection(monilia), no_presence=True)

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")
    assert_nothing_saved(monitoring)


@pytest.mark.parametrize("both", [True, False])
def test_a_detection_is_either_a_pest_or_other(client, monitoring, monilia, both):
    row = detection(monilia, other="Hormigas") if both else detection()

    assert_rejected(client.post(url(monitoring), result(row), format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_the_same_pest_cannot_be_twice(client, monitoring, monilia):
    body = result(detection(monilia, 3), detection(monilia, 5))

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_the_same_other_written_differently_cannot_be_twice(client, monitoring):
    body = result(detection(other="Hormigas en hojas"), detection(other="HORMIGAS  en hojás"))

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_other_has_at_most_100_characters(client, monitoring):
    body = result(detection(other="H" * 101))

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")


def test_the_notes_have_at_most_500_characters(client, monitoring, monilia):
    body = result(detection(monilia), notes="N" * 501)

    assert_rejected(client.post(url(monitoring), body, format="json"), "notes")


def test_a_pest_that_does_not_exist_is_a_400_not_a_404(client, monitoring):
    row = detection()
    row["pest_disease_id"] = str(uuid.uuid4())

    assert_rejected(client.post(url(monitoring), result(row), format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_an_inactive_pest_is_a_422_with_the_affected_ones(client, monitoring, monilia, trips):
    trips.is_active = False
    trips.save()

    response = client.post(
        url(monitoring), result(detection(monilia), detection(trips)), format="json"
    )

    assert response.status_code == 422
    assert response.data["code"] == "pest_disease_inactive"
    assert response.data["pest_disease_ids"] == [str(trips.pk)]
    assert_nothing_saved(monitoring)


def test_the_same_detection_id_cannot_be_twice(client, monitoring, monilia, trips):
    repeated = uuid.uuid4()
    body = result(
        detection(monilia, detection_id=repeated), detection(trips, detection_id=repeated)
    )

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_a_detection_id_used_in_another_monitoring_is_a_400(client, monitoring, monilia):
    taken = DetectionFactory()

    body = result(detection(monilia, detection_id=taken.pk))

    assert_rejected(client.post(url(monitoring), body, format="json"), "detections")
    assert_nothing_saved(monitoring)


def test_a_future_date_is_rejected(client, monitoring, monilia):
    body = result(detection(monilia), done_date=str(today_in_bogota() + timedelta(days=1)))

    assert_rejected(client.post(url(monitoring), body, format="json"), "done_date")
    assert_nothing_saved(monitoring)


def test_unknown_fields_are_rejected(client, monitoring, monilia):
    body = result(detection(monilia), severity="alta")

    assert_rejected(client.post(url(monitoring), body, format="json"), "severity")


def test_another_activity_is_not_a_monitoring(client, plot, owner, monilia):
    pruning = AgriculturalActivityFactory(plot=plot, assignee=owner)

    response = client.post(url(pruning), result(detection(monilia)), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "not_a_monitoring"


def test_a_monitoring_that_does_not_exist_is_a_404(client, monilia):
    missing = AgriculturalActivity(pk=uuid.uuid4())

    response = client.post(url(missing), result(detection(monilia)), format="json")

    assert response.status_code == 404


# --- Reintentos ---------------------------------------------------------------------------------


def test_the_same_result_sent_again_is_a_200_without_changes(client, monitoring, monilia, trips):
    body = result(detection(monilia, 12), detection(trips, 3))
    client.post(url(monitoring), body, format="json")
    monitoring.refresh_from_db()
    version = monitoring.version

    # La cola puede reenviar las detecciones en otro orden: sigue siendo el mismo envío.
    again = {**body, "detections": list(reversed(body["detections"]))}
    response = client.post(url(monitoring), again, format="json")

    assert response.status_code == 200
    monitoring.refresh_from_db()
    assert monitoring.version == version
    assert Detection.objects.count() == 2


def test_another_result_on_a_recorded_monitoring_is_a_409(client, monitoring, monilia):
    body = result(detection(monilia, 12))
    client.post(url(monitoring), body, format="json")

    other = {**body, "detections": [{**body["detections"][0], "affected_units": 13}]}
    response = client.post(url(monitoring), other, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "activity_already_done"
    assert stored(monitoring).detections.get().affected_units == 12


# --- Quién registra -----------------------------------------------------------------------------


@pytest.fixture
def farm(plot):
    return plot.farm


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


def test_the_foreman_of_the_farm_records_it(auth_client, monitoring, farm, monilia):
    response = auth_client(foreman_of(farm)).post(
        url(monitoring), result(detection(monilia)), format="json"
    )

    assert response.status_code == 201


def test_a_custom_role_that_schedules_records_it_whatever_its_name(
    auth_client, monitoring, farm, monilia
):
    admin_role = make_delegate(farm.producer, [COMPLETE, SCHEDULE], farm=farm)

    response = auth_client(admin_role).post(
        url(monitoring), result(detection(monilia)), format="json"
    )

    assert response.status_code == 201


def test_the_assignee_records_their_own(auth_client, plot, farm, monilia):
    worker = make_delegate(farm.producer, [COMPLETE], farm=farm)
    own = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING, assignee=worker
    )

    response = auth_client(worker).post(url(own), result(detection(monilia)), format="json")

    assert response.status_code == 201


def test_a_worker_does_not_record_a_colleague_s_monitoring(auth_client, monitoring, farm, monilia):
    worker = make_delegate(farm.producer, [COMPLETE], farm=farm)

    response = auth_client(worker).post(url(monitoring), result(detection(monilia)), format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert_nothing_saved(monitoring)


def test_without_the_permission_to_record_it_is_a_403(auth_client, monitoring, farm, monilia):
    viewer = make_delegate(farm.producer, ["activities.view_agriculturalactivity"], farm=farm)

    response = auth_client(viewer).post(url(monitoring), result(detection(monilia)), format="json")

    assert response.status_code == 403


def test_the_foreman_of_another_farm_gets_a_404(auth_client, monitoring, farm, monilia):
    other_farm = FarmFactory(producer=farm.producer)

    response = auth_client(foreman_of(other_farm)).post(
        url(monitoring), result(detection(monilia)), format="json"
    )

    assert response.status_code == 404


def test_another_producer_gets_a_404(auth_client, monitoring, monilia):
    stranger = make_producer_owner(ProducerFactory())

    response = auth_client(stranger).post(
        url(monitoring), result(detection(monilia)), format="json"
    )

    assert response.status_code == 404


def test_the_association_cannot_record_monitorings(auth_client, monitoring, monilia):
    response = auth_client(make_administrator()).post(
        url(monitoring), result(detection(monilia)), format="json"
    )

    assert response.status_code == 403


def test_without_a_session_it_is_a_401(api_client, monitoring, monilia):
    response = api_client.post(url(monitoring), result(detection(monilia)), format="json")

    assert response.status_code == 401


def test_the_generic_completion_still_asks_for_the_result(client, monitoring):
    response = client.post(
        f"/api/agricultural-activities/{monitoring.pk}/completion",
        {"done_date": str(today_in_bogota())},
        format="json",
    )

    assert response.status_code == 422
    assert response.data["code"] == "monitoring_requires_result"
