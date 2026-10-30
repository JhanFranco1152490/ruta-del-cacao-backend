"""Los desvíos de la fermentación: cuándo un volteo avisa por su temperatura o por el pH del
grano, a quién, y qué responde la API al guardarlo."""

import logging
import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.fermentation import alerts as fermentation_alerts
from apps.fermentation.alerts import measurement_deviations, turn_alerts, turn_deviations
from apps.fermentation.tests.factories import FermentationProcessFactory, FermentationTurnFactory
from apps.notifications.models import Notification
from apps.postharvest_parameters.baseline import FERMENTATION_BASELINE
from apps.postharvest_parameters.tests.factories import PostharvestParametersFactory

from .helpers import Farmstead

pytestmark = pytest.mark.django_db


def kinds(deviations):
    return [deviation.kind for deviation in deviations]


def check(temperature="45.0", ph="4.90", hours=50, parameters=FERMENTATION_BASELINE):
    return measurement_deviations(
        Decimal(temperature), Decimal(ph), timedelta(hours=hours), parameters
    )


# La regla, con la línea base.


def test_a_normal_turn_has_no_deviation():
    assert check() == []


@pytest.mark.parametrize(
    ("temperature", "expected"),
    [
        ("39.9", ["fermentation_temperature_low"]),
        ("40.0", []),
        ("50.0", []),
        ("50.1", ["fermentation_temperature_high"]),
    ],
)
def test_the_temperature_range_is_closed(temperature, expected):
    assert kinds(check(temperature=temperature)) == expected


def test_a_temperature_deviation_says_its_value_and_limit():
    (low,) = check(temperature="37.5")
    (high,) = check(temperature="53.0")

    assert (low.value, low.limit, low.severity) == ("37.5", "40.0", "normal")
    assert (high.value, high.limit, high.severity) == ("53.0", "50.0", "normal")


def test_a_cold_first_turn_already_warns():
    # Desde el primer volteo: si en una región fría es lo normal, el productor baja su mínimo.
    assert kinds(check(temperature="38.0", hours=48)) == ["fermentation_temperature_low"]


@pytest.mark.parametrize("hours", [48, 120])
def test_a_too_acid_grain_warns_on_any_turn(hours):
    (acid,) = check(ph="3.99", hours=hours)

    assert acid.kind == "fermentation_ph_low"
    assert (acid.value, acid.limit) == ("3.99", "4.00")
    assert check(ph="4.00", hours=hours) == []


def test_a_high_ph_is_normal_in_the_first_days():
    assert check(ph="6.40", hours=48) == []
    assert check(ph="5.51", hours=95.99) == []


def test_a_high_ph_from_the_fourth_day_means_the_fermentation_is_not_advancing():
    (stuck,) = check(ph="5.51", hours=96)

    assert stuck.kind == "fermentation_ph_high"
    assert (stuck.value, stuck.limit) == ("5.51", "5.50")
    assert check(ph="5.50", hours=98) == []


def test_one_turn_can_have_a_temperature_and_a_ph_deviation():
    assert kinds(check(temperature="53.0", ph="6.10", hours=98)) == [
        "fermentation_temperature_high",
        "fermentation_ph_high",
    ]


def test_the_producer_range_is_the_one_used():
    stricter = replace(FERMENTATION_BASELINE, ph_min=Decimal("4.50"))

    assert kinds(check(ph="4.30", parameters=stricter)) == ["fermentation_ph_low"]
    assert check(ph="4.30") == []


# Los parámetros del productor y los fallos.


@pytest.fixture
def process():
    return FermentationProcessFactory(started_at=timezone.now() - timedelta(hours=120))


def turn_at(process, hours, temperature="45.0", ph="4.90"):
    return FermentationTurnFactory(
        process=process,
        turned_at=process.started_at + timedelta(hours=hours),
        temperature_c=Decimal(temperature),
        ph=Decimal(ph),
    )


def test_it_reads_the_range_of_the_lot_producer(process):
    PostharvestParametersFactory(
        producer=process.lot.harvest.plot.farm.producer, ph_min=Decimal("4.50")
    )

    assert kinds(turn_deviations(turn_at(process, 50, ph="4.30"))) == ["fermentation_ph_low"]


def test_it_counts_the_hours_from_the_start_of_its_fermentation(process):
    assert kinds(turn_deviations(turn_at(process, 98, ph="6.10"))) == ["fermentation_ph_high"]
    assert turn_deviations(turn_at(process, 60, ph="6.10")) == []


def test_a_failure_while_evaluating_gives_no_deviation_and_is_logged(process, monkeypatch, caplog):
    turn = turn_at(process, 50, temperature="53.0")
    # El dato llega en una variable, como llegaría de la base: el traceback muestra la línea de
    # código, y en código real nunca hay datos personales escritos.
    message = f"documento {1090123456}"

    def broken(producer_id):
        raise ValueError(message)

    monkeypatch.setattr(fermentation_alerts, "fermentation_parameters", broken)
    with caplog.at_level(logging.ERROR):
        assert turn_deviations(turn) == []

    assert "ValueError" in caplog.text
    assert "1090123456" not in caplog.text


# Quién recibe el aviso.


@pytest.fixture
def place():
    place = Farmstead()
    place.process = FermentationProcessFactory(
        lot=place.lot,
        facility=place.box,
        responsible=place.foreman,
        started_at=timezone.now() - timedelta(hours=120),
    )
    return place


def test_the_producer_the_responsible_and_who_turns_in_the_farm_are_told(place):
    turner = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)
    make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_b)
    turn = turn_at(place.process, 50, temperature="53.0")

    drafts = turn_alerts(turn)

    # El capataz es el responsable y además voltea en la finca: recibe uno solo.
    assert sorted(draft.recipient_id for draft in drafts) == sorted(
        [place.owner.pk, place.foreman.pk, turner.pk]
    )


def test_each_draft_points_to_its_lot_and_its_turn(place):
    turn = turn_at(place.process, 98, ph="6.10")

    draft = next(d for d in turn_alerts(turn) if d.recipient_id == place.owner.pk)

    assert draft.kind == "fermentation_ph_high"
    assert draft.severity == "normal"
    assert draft.condition_key == f"{turn.pk}:fermentation_ph_high"
    assert draft.thread_key == f"lot:{place.lot.pk}:fermentation_ph_high"
    assert (draft.lot_id, draft.fermentation_turn_id) == (place.lot.pk, turn.pk)
    assert draft.condition_at == turn.turned_at


def test_a_normal_turn_tells_nobody(place):
    assert turn_alerts(turn_at(place.process, 50)) == []


# Al guardar por la API.


@pytest.fixture
def started(auth_client):
    """Una fermentación iniciada por la API hace 130 horas, todavía sin volteos."""
    place = Farmstead()
    place.started_at = (timezone.now() - timedelta(hours=130)).replace(second=0, microsecond=0)
    body = place.start_body(started_at=place.started_at.isoformat())
    response = auth_client(place.owner).post("/api/fermentation", body, format="json")
    assert response.status_code == 201, response.data
    return place


def turn_body(place, hours, temperature="45.0", ph="4.90"):
    return {
        "id": str(uuid.uuid4()),
        "turned_at": (place.started_at + timedelta(hours=hours)).isoformat(),
        "temperature_c": temperature,
        "ph": ph,
    }


def register(client, place, body):
    return client.post(f"/api/fermentation/{place.lot.pk}/turns", body, format="json")


def test_saving_a_turn_answers_with_its_deviations(auth_client, started):
    body = turn_body(started, 98, temperature="53.0", ph="6.10")

    response = register(auth_client(started.foreman), started, body)

    assert response.status_code == 201, response.data
    assert response.data["alerts"] == [
        {
            "kind": "fermentation_temperature_high",
            "severity": "normal",
            "value": "53.0",
            "limit": "50.0",
        },
        {"kind": "fermentation_ph_high", "severity": "normal", "value": "6.10", "limit": "5.50"},
    ]
    assert response.data["number"] == 1


def test_a_normal_turn_answers_with_no_deviations(auth_client, started):
    response = register(auth_client(started.foreman), started, turn_body(started, 50))

    assert response.status_code == 201, response.data
    assert response.data["alerts"] == []


def test_sending_the_same_turn_again_answers_with_its_deviations_too(auth_client, started):
    client = auth_client(started.foreman)
    body = turn_body(started, 50, ph="3.90")
    register(client, started, body)

    again = register(client, started, body)

    assert again.status_code == 200, again.data
    assert [alert["kind"] for alert in again.data["alerts"]] == ["fermentation_ph_low"]


def test_a_failure_while_evaluating_still_saves_the_turn(auth_client, started, monkeypatch):
    def broken(producer_id):
        raise ValueError("falla")

    monkeypatch.setattr(fermentation_alerts, "fermentation_parameters", broken)

    response = register(auth_client(started.foreman), started, turn_body(started, 50, "53.0"))

    assert response.status_code == 201, response.data
    assert response.data["alerts"] == []


def test_the_producer_is_told_once_the_turn_is_saved(
    auth_client, started, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        register(auth_client(started.foreman), started, turn_body(started, 50, ph="3.90"))

    acid = Notification.objects.get(recipient=started.owner, kind="fermentation_ph_low")
    assert acid.lot_id == started.lot.pk


def test_a_ph_that_keeps_high_warns_again_and_replaces_the_previous(
    auth_client, started, django_capture_on_commit_callbacks
):
    client = auth_client(started.foreman)
    with django_capture_on_commit_callbacks(execute=True):
        register(client, started, turn_body(started, 98, ph="6.10"))
    with django_capture_on_commit_callbacks(execute=True):
        register(client, started, turn_body(started, 122, ph="6.00"))

    warnings = Notification.objects.filter(recipient=started.owner, kind="fermentation_ph_high")
    assert warnings.count() == 2
    assert warnings.filter(dismissed_at__isnull=True).get().fermentation_turn.ph == Decimal("6.00")


def test_correcting_a_turn_withdraws_what_it_no_longer_is(
    auth_client, started, django_capture_on_commit_callbacks
):
    client = auth_client(started.foreman)
    with django_capture_on_commit_callbacks(execute=True):
        logged = register(client, started, turn_body(started, 50, temperature="53.0")).data
    assert Notification.objects.filter(kind="fermentation_temperature_high").exists()

    with django_capture_on_commit_callbacks(execute=True):
        response = client.patch(
            f"/api/fermentation/{started.lot.pk}/turns/{logged['id']}",
            {"temperature_c": "48.0", "expected_version": logged["version"]},
            format="json",
        )

    assert response.status_code == 200, response.data
    assert response.data["alerts"] == []
    assert not Notification.objects.filter(kind="fermentation_temperature_high").exists()


def test_a_failure_while_correcting_withdraws_nothing(
    auth_client, started, monkeypatch, django_capture_on_commit_callbacks
):
    # Si no se pueden calcular los desvíos, no se sabe cuáles ya no cumple: no se retira ninguno.
    client = auth_client(started.foreman)
    with django_capture_on_commit_callbacks(execute=True):
        logged = register(client, started, turn_body(started, 50, temperature="53.0")).data

    def broken(producer_id):
        raise ValueError("falla")

    monkeypatch.setattr(fermentation_alerts, "fermentation_parameters", broken)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.patch(
            f"/api/fermentation/{started.lot.pk}/turns/{logged['id']}",
            {"notes": "Corregido.", "expected_version": logged["version"]},
            format="json",
        )

    assert response.status_code == 200, response.data
    assert Notification.objects.filter(kind="fermentation_temperature_high").exists()
