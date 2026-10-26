"""Los desvíos del secado: cuándo una bitácora avisa, a quién, y qué responde la API al
guardarla."""

import logging
import uuid
from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.drying import alerts as drying_alerts
from apps.drying.alerts import drying_log_alerts, log_deviations, moisture_deviations
from apps.drying.tests.factories import DryingLogEntryFactory, DryingProcessFactory
from apps.notifications.models import Notification
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.tests.factories import PostharvestParametersFactory

from .helpers import Farmstead, fermented_lot

pytestmark = pytest.mark.django_db


def kinds(deviations):
    return {deviation.kind for deviation in deviations}


def check(moisture, day=4, drop=None, parameters=DRYING_BASELINE):
    return moisture_deviations(
        Decimal(moisture), day, None if drop is None else Decimal(drop), parameters
    )


# La regla, con la línea base.


def test_a_normal_measurement_has_no_deviation():
    assert check("30.0", day=4, drop="6.0") == []


def test_overdrying_is_critical_and_says_its_limit():
    (overdried,) = check("5.8", day=5)

    assert overdried.kind == "drying_overdried"
    assert overdried.severity == "critical"
    assert (overdried.value, overdried.limit) == ("5.8", "6.0")
    assert check("6.0", day=5) == []


@pytest.mark.parametrize(
    ("moisture", "expected"), [("7.5", False), ("7.6", True), ("8.5", True), ("8.6", False)]
)
def test_near_target_is_a_closed_range(moisture, expected):
    deviations = check(moisture, day=5)

    assert ("drying_near_target" in kinds(deviations)) is expected
    if expected:
        assert deviations[0].limit == "7.6-8.5"


@pytest.mark.parametrize(
    ("moisture", "day", "expected"),
    [("14.9", 3, True), ("14.9", 4, False), ("15.0", 3, False), ("14.9", 1, True)],
)
def test_accelerated_drying_is_fast_in_the_first_days(moisture, day, expected):
    assert ("drying_accelerated" in kinds(check(moisture, day=day))) is expected


@pytest.mark.parametrize(
    ("moisture", "day", "expected"),
    [("10.1", 8, True), ("10.0", 8, False), ("12.0", 7, False), ("10.1", 11, True)],
)
def test_slow_drying_by_duration_is_still_wet_late(moisture, day, expected):
    assert ("drying_slow_duration" in kinds(check(moisture, day=day))) is expected


def test_slow_drying_by_stalling_compares_with_48_hours_before():
    (stalled,) = check("30.0", day=4, drop="2.1")

    assert stalled.kind == "drying_slow_stalled"
    assert (stalled.value, stalled.limit) == ("2.1", "4.0")
    assert check("30.0", day=4, drop="4.0") == []
    # Sin una medición de 48 horas antes no se evalúa.
    assert check("30.0", day=4, drop=None) == []


def test_one_measurement_can_be_several_deviations():
    assert kinds(check("5.8", day=2)) == {"drying_accelerated", "drying_overdried"}


def test_the_producer_thresholds_are_the_ones_used():
    stricter = replace(DRYING_BASELINE, overdried_moisture_pct=Decimal("6.5"))

    assert kinds(check("6.2", day=5, parameters=stricter)) == {"drying_overdried"}
    assert check("6.2", day=5) == []


# La medición con la que se compara y los parámetros del productor.


@pytest.fixture
def process():
    return DryingProcessFactory(started_at=timezone.now() - timedelta(hours=150))


def log_at(process, hours, moisture, day):
    measured_at = process.started_at + timedelta(hours=hours)
    return DryingLogEntryFactory(
        process=process,
        day=day,
        measured_at=measured_at,
        log_date=timezone.localdate(measured_at),
        moisture_pct=Decimal(moisture),
    )


def test_it_compares_with_the_latest_measurement_48_hours_or_more_before(process):
    log_at(process, 46, "40.0", day=2)  # 74 h antes
    log_at(process, 70, "31.5", day=3)  # 50 h antes: la que cuenta
    log_at(process, 94, "30.5", day=4)  # 26 h antes: muy cerca
    entry = log_at(process, 120, "30.0", day=5)

    (stalled,) = log_deviations(entry)

    assert stalled.kind == "drying_slow_stalled"
    assert stalled.value == "1.5"


def test_without_a_measurement_48_hours_before_stalling_is_not_evaluated(process):
    log_at(process, 94, "30.5", day=4)
    entry = log_at(process, 120, "30.0", day=5)

    assert log_deviations(entry) == []


def test_it_reads_the_thresholds_of_the_lot_producer(process):
    PostharvestParametersFactory(
        producer=process.lot.harvest.plot.farm.producer, overdried_moisture_pct=Decimal("6.5")
    )
    entry = log_at(process, 120, "6.2", day=5)

    assert kinds(log_deviations(entry)) == {"drying_overdried"}


def test_a_failure_while_evaluating_gives_no_deviation_and_is_logged(process, monkeypatch, caplog):
    entry = log_at(process, 120, "5.8", day=5)
    # El dato llega en una variable, como llegaría de la base: el traceback muestra la línea de
    # código, y en código real nunca hay datos personales escritos.
    message = f"documento {1090123456}"

    def broken(producer_id):
        raise ValueError(message)

    monkeypatch.setattr(drying_alerts, "drying_parameters", broken)
    with caplog.at_level(logging.ERROR):
        assert log_deviations(entry) == []

    assert "ValueError" in caplog.text
    assert "1090123456" not in caplog.text


# Quién recibe el aviso.


@pytest.fixture
def place():
    place = Farmstead()
    place.process = DryingProcessFactory(
        lot=fermented_lot(place.plot_a, actor=place.owner),
        facility=place.dryer,
        responsible=place.foreman,
        started_at=timezone.now() - timedelta(hours=150),
    )
    return place


def test_the_producer_the_responsible_and_who_logs_in_the_farm_are_told(place):
    logger = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_a)
    make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_b)
    inactive = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_a)
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    entry = log_at(place.process, 120, "5.8", day=5)

    drafts = drying_log_alerts(entry)

    # El capataz es el responsable y además registra en la finca: recibe uno solo.
    assert sorted(draft.recipient_id for draft in drafts) == sorted(
        [place.owner.pk, place.foreman.pk, logger.pk]
    )


def test_each_draft_points_to_its_lot_and_its_log(place):
    entry = log_at(place.process, 120, "5.8", day=5)

    draft = next(d for d in drying_log_alerts(entry) if d.recipient_id == place.owner.pk)

    assert draft.kind == "drying_overdried"
    assert draft.severity == "critical"
    assert draft.condition_key == f"{entry.pk}:drying_overdried"
    assert draft.thread_key == f"lot:{place.process.lot_id}:drying_overdried"
    assert draft.lot_id == place.process.lot_id
    assert draft.drying_log_id == entry.pk
    assert draft.condition_at == entry.measured_at


def test_a_normal_log_tells_nobody(place):
    entry = log_at(place.process, 120, "30.0", day=5)

    assert drying_log_alerts(entry) == []


# Al guardar por la API.


@pytest.fixture
def started(auth_client):
    """Un secado iniciado por la API hace cinco días a las 14:00, todavía sin bitácora: el día 4
    ya pasó entero, a cualquier hora que corra la prueba."""
    place = Farmstead()
    place.lot = fermented_lot(place.plot_a, actor=place.owner, hours_ago=150)
    place.start_day = timezone.localdate() - timedelta(days=5)
    started_at = timezone.make_aware(datetime.combine(place.start_day, time(14, 0)))
    body = place.start_body(started_at=started_at.isoformat())
    response = auth_client(place.owner).post("/api/drying", body, format="json")
    assert response.status_code == 201, response.data
    return place


def log_body(place, day, moisture):
    measured_at = timezone.make_aware(
        datetime.combine(place.start_day + timedelta(days=day - 1), time(17, 0))
    )
    return {
        "id": str(uuid.uuid4()),
        "measured_at": measured_at.isoformat(),
        "moisture_pct": moisture,
        "sun_hours": "5.0",
        "turn_count": 3,
        "turn_frequency_hours": "1.5",
        "weather": "sunny",
    }


def register(client, place, body):
    return client.post(f"/api/drying/{place.lot.pk}/logs", body, format="json")


def test_saving_a_log_answers_with_its_deviations(auth_client, started):
    response = register(auth_client(started.foreman), started, log_body(started, 2, "5.8"))

    assert response.status_code == 201, response.data
    assert response.data["alerts"] == [
        {"kind": "drying_accelerated", "severity": "normal", "value": "5.8", "limit": "15.0"},
        {"kind": "drying_overdried", "severity": "critical", "value": "5.8", "limit": "6.0"},
    ]
    assert response.data["day_number"] == 2


def test_a_normal_log_answers_with_no_deviations(auth_client, started):
    response = register(auth_client(started.foreman), started, log_body(started, 2, "45.0"))

    assert response.status_code == 201, response.data
    assert response.data["alerts"] == []


def test_sending_the_same_log_again_answers_with_its_deviations_too(auth_client, started):
    client = auth_client(started.foreman)
    body = log_body(started, 2, "5.8")
    register(client, started, body)

    again = register(client, started, body)

    assert again.status_code == 200, again.data
    assert {alert["kind"] for alert in again.data["alerts"]} == {
        "drying_accelerated",
        "drying_overdried",
    }


def test_a_failure_while_evaluating_still_saves_the_log(auth_client, started, monkeypatch):
    def broken(producer_id):
        raise ValueError("falla")

    monkeypatch.setattr(drying_alerts, "drying_parameters", broken)

    response = register(auth_client(started.foreman), started, log_body(started, 2, "5.8"))

    assert response.status_code == 201, response.data
    assert response.data["alerts"] == []


def test_the_producer_is_told_once_the_log_is_saved(
    auth_client, started, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        register(auth_client(started.foreman), started, log_body(started, 2, "5.8"))

    overdried = Notification.objects.get(recipient=started.owner, kind="drying_overdried")
    assert overdried.severity == "critical"
    assert overdried.lot_id == started.lot.pk


def test_correcting_a_log_withdraws_what_it_no_longer_is(
    auth_client, started, django_capture_on_commit_callbacks
):
    client = auth_client(started.foreman)
    with django_capture_on_commit_callbacks(execute=True):
        logged = register(client, started, log_body(started, 4, "5.8")).data
    assert Notification.objects.filter(kind="drying_overdried").exists()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.patch(
            f"/api/drying/{started.lot.pk}/logs/{logged['id']}",
            {"moisture_pct": "7.0", "expected_version": logged["version"]},
            format="json",
        )

    assert response.status_code == 200, response.data
    assert response.data["alerts"] == []
    assert not Notification.objects.filter(kind="drying_overdried").exists()


def test_correcting_into_another_deviation_tells_it(
    auth_client, started, django_capture_on_commit_callbacks
):
    client = auth_client(started.foreman)
    with django_capture_on_commit_callbacks(execute=True):
        logged = register(client, started, log_body(started, 4, "5.8")).data

    with django_capture_on_commit_callbacks(execute=True):
        response = client.patch(
            f"/api/drying/{started.lot.pk}/logs/{logged['id']}",
            {"moisture_pct": "8.1", "expected_version": logged["version"]},
            format="json",
        )

    assert [alert["kind"] for alert in response.data["alerts"]] == ["drying_near_target"]
    assert set(Notification.objects.values_list("kind", flat=True)) == {"drying_near_target"}
