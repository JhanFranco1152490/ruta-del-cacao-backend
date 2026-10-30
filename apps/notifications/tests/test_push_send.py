import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone
from py_vapid import Vapid02
from pywebpush import WebPushException

from apps.accounts.system_roles import PRODUCER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.common.contracts.alerts import NotificationDraft
from apps.drying.tests.factories import DryingLogEntryFactory
from apps.farms.tests.factories import FarmFactory
from apps.lots.tests.factories import LotFactory
from apps.notifications.models import Notification, PushSubscription
from apps.notifications.push import send
from apps.notifications.push.send import send_pending_pushes
from apps.notifications.services import create
from apps.notifications.services.create import create_notifications
from apps.notifications.services.evaluate import evaluate_alerts
from apps.notifications.tests.factories import (
    LotNotificationFactory,
    NotificationFactory,
    PushSubscriptionFactory,
)
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

# 11:05 UTC son las 6:05 en Bogotá: la primera hora con push.
MORNING = datetime(2026, 10, 16, 11, 5, tzinfo=UTC)
VIEW = "activities.view_agriculturalactivity"


@pytest.fixture(autouse=True)
def vapid(settings):
    settings.VAPID_PUBLIC_KEY = "BPublica"
    settings.VAPID_PRIVATE_KEY = "privada"
    settings.VAPID_SUBJECT = "mailto:equipo@example.com"


class Sent(list):
    """Las push que se habrían enviado, (dirección, contenido); `failures` dice qué
    dispositivos responden con un error y cuál."""

    def __init__(self):
        super().__init__()
        self.failures = {}
        self.errors = {}


@pytest.fixture
def sent(monkeypatch):
    # Nada sale a la red.
    calls = Sent()

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl, timeout):
        endpoint = subscription_info["endpoint"]
        if endpoint in calls.errors:
            raise calls.errors[endpoint]
        assert vapid_private_key == "privada"
        assert vapid_claims == {"sub": "mailto:equipo@example.com"}
        if endpoint in calls.failures:
            response = SimpleNamespace(status_code=calls.failures[endpoint])
            raise WebPushException("fallo", response=response)
        calls.append((endpoint, json.loads(data)))

    monkeypatch.setattr(send, "webpush", fake_webpush)
    return calls


def pending(recipient=None, created=MORNING, **kwargs):
    activity = kwargs.pop("activity", None) or AgriculturalActivityFactory()
    recipient = recipient or activity.assignee
    # Quien recibe la push alcanza la actividad: si no, el aviso no se ve en su bandeja.
    recipient.producer = activity.plot.farm.producer
    recipient.save(update_fields=["producer"])
    grant_role(recipient, get_system_role(PRODUCER))
    notification = NotificationFactory(recipient=recipient, activity=activity, **kwargs)
    Notification.objects.filter(pk=notification.pk).update(created_at=created)
    return notification


def pushed(notification):
    notification.refresh_from_db()
    return notification.pushed_at


def test_a_new_notification_reaches_every_device_of_its_recipient(sent):
    notification = pending()
    phone = PushSubscriptionFactory(user=notification.recipient)
    laptop = PushSubscriptionFactory(user=notification.recipient)

    result = send_pending_pushes(MORNING)

    assert {endpoint for endpoint, _ in sent} == {phone.endpoint, laptop.endpoint}
    assert sent[0][1]["title"] == "Tu actividad está vencida"
    assert pushed(notification) == MORNING
    assert (result.sent, result.failed) == (2, 0)
    phone.refresh_from_db()
    assert phone.last_success_at == MORNING


def test_the_payload_carries_only_what_the_phone_shows(sent):
    notification = pending(recipient=UserFactory(first_name="Luis", last_name="Mora"))
    notification.activity.assignee = notification.recipient
    notification.activity.save()
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(MORNING)

    [(_, payload)] = sent
    assert set(payload) == {"title", "body", "url", "tag"}
    assert "Luis" not in json.dumps(payload)
    assert "Mora" not in json.dumps(payload)


def test_several_new_ones_go_as_one_summary(sent):
    recipient = UserFactory()
    first = pending(recipient=recipient)
    farm = first.activity.plot.farm
    pending(recipient=recipient, activity=AgriculturalActivityFactory(plot=PlotFactory(farm=farm)))
    PushSubscriptionFactory(user=recipient)

    send_pending_pushes(MORNING)

    [(_, payload)] = sent
    assert payload["title"] == "Tienes 2 avisos nuevos"


@pytest.mark.parametrize(
    "hour_utc, minute, sends",
    [(10, 59, False), (11, 0, True), (23, 59, True), (0, 0, False)],
)
def test_pushes_go_out_only_from_six_to_seven_pm_in_bogota(sent, hour_utc, minute, sends):
    # 6:00 en Bogotá son las 11:00 UTC; las 19:00, las 00:00 UTC del día siguiente.
    now = datetime(2026, 10, 16, hour_utc, minute, tzinfo=UTC)
    notification = pending(created=now)
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(now)

    assert bool(sent) is sends
    assert (pushed(notification) is not None) is sends


def test_what_was_created_at_night_goes_out_in_the_morning(sent):
    notification = pending(created=MORNING - timedelta(hours=6))
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(MORNING)

    assert len(sent) == 1


def test_a_read_or_dismissed_one_is_not_pushed(sent):
    read = pending(read_at=MORNING)
    dismissed = pending(dismissed_at=MORNING)
    PushSubscriptionFactory(user=read.recipient)
    PushSubscriptionFactory(user=dismissed.recipient)

    send_pending_pushes(MORNING)

    assert sent == []


def test_one_older_than_a_day_is_not_pushed(sent):
    notification = pending(created=MORNING - timedelta(hours=25))
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(MORNING)

    assert sent == []


def test_without_devices_nothing_is_sent_and_nothing_breaks(sent):
    notification = pending()

    send_pending_pushes(MORNING)

    assert sent == []
    assert pushed(notification) is None


def test_sending_twice_does_not_repeat(sent):
    notification = pending()
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(MORNING)
    send_pending_pushes(MORNING + timedelta(hours=1))

    assert len(sent) == 1


def test_a_device_that_is_gone_is_forgotten(sent):
    notification = pending()
    gone = PushSubscriptionFactory(user=notification.recipient)
    sent.failures[gone.endpoint] = 410

    send_pending_pushes(MORNING)

    assert not PushSubscription.objects.filter(pk=gone.pk).exists()


def test_another_failure_is_retried_the_next_hour(sent):
    notification = pending()
    device = PushSubscriptionFactory(user=notification.recipient)
    sent.failures[device.endpoint] = 500

    result = send_pending_pushes(MORNING)

    assert result.failed == 1
    assert pushed(notification) is None
    assert PushSubscription.objects.filter(pk=device.pk).exists()

    del sent.failures[device.endpoint]
    send_pending_pushes(MORNING + timedelta(hours=1))

    assert len(sent) == 1


def test_one_device_that_works_is_enough(sent):
    notification = pending()
    broken = PushSubscriptionFactory(user=notification.recipient)
    PushSubscriptionFactory(user=notification.recipient)
    sent.failures[broken.endpoint] = 500

    send_pending_pushes(MORNING)

    assert pushed(notification) == MORNING


def test_an_inactive_account_gets_nothing_and_loses_its_devices(sent):
    inactive = UserFactory(is_active=False)
    notification = pending(recipient=inactive)
    device = PushSubscriptionFactory(user=inactive)

    send_pending_pushes(MORNING)

    assert sent == []
    assert pushed(notification) is None
    assert not PushSubscription.objects.filter(pk=device.pk).exists()


def test_without_keys_push_is_off(sent, settings):
    settings.VAPID_PRIVATE_KEY = ""
    notification = pending()
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(MORNING)

    assert sent == []
    assert pushed(notification) is None


def test_the_claimed_ones_are_taken_only_once():
    # Dos evaluaciones a la vez: la segunda ya no encuentra lo que tomó la primera.
    notification = pending()
    PushSubscriptionFactory(user=notification.recipient)

    first = send.claim_pending(MORNING)
    second = send.claim_pending(MORNING)

    assert [n.pk for n in first] == [notification.pk]
    assert second == []


def test_each_activity_reaches_its_own_people(sent):
    activity = AgriculturalActivityFactory()
    foreman = UserFactory(producer=activity.plot.farm.producer)
    pending(recipient=activity.assignee, activity=activity)
    pending(recipient=foreman, activity=activity)
    PushSubscriptionFactory(user=activity.assignee, endpoint="https://fcm.googleapis.com/a")
    PushSubscriptionFactory(user=foreman, endpoint="https://fcm.googleapis.com/b")

    send_pending_pushes(MORNING)

    titles = {endpoint: payload["title"] for endpoint, payload in sent}
    assert titles == {
        "https://fcm.googleapis.com/a": "Tu actividad está vencida",
        "https://fcm.googleapis.com/b": "Actividad vencida",
    }


def test_the_generated_keys_are_the_ones_the_library_takes(capsys):
    # Las llaves que imprime el comando son las que acepta la librería, sin convertir nada.
    call_command("generate_vapid_keys")
    lines = dict(line.split("=", 1) for line in capsys.readouterr().out.split())

    assert len(lines["VAPID_PUBLIC_KEY"]) == 87
    assert Vapid02.from_string(private_key=lines["VAPID_PRIVATE_KEY"]).public_key is not None


def test_a_push_failure_does_not_stop_the_evaluation(monkeypatch):
    def broken(now):
        raise RuntimeError("caído")

    monkeypatch.setattr("apps.notifications.services.evaluate.send_pending_pushes", broken)
    result = evaluate_alerts(MORNING.date(), MORNING)

    assert result.failed == []


def test_an_unexpected_error_on_one_device_does_not_lose_the_others(sent):
    notification = pending()
    broken = PushSubscriptionFactory(user=notification.recipient)
    working = PushSubscriptionFactory(user=notification.recipient)
    sent.errors[broken.endpoint] = ValueError("llave inválida")

    result = send_pending_pushes(MORNING)

    assert [endpoint for endpoint, _ in sent] == [working.endpoint]
    assert (result.sent, result.failed) == (1, 1)
    assert pushed(notification) == MORNING


def test_an_unexpected_error_is_retried_the_next_hour(sent):
    first = pending()
    device = PushSubscriptionFactory(user=first.recipient)
    second = pending()
    PushSubscriptionFactory(user=second.recipient)
    sent.errors[device.endpoint] = ValueError("llave inválida")

    result = send_pending_pushes(MORNING)

    assert result.failed == 1
    assert len(sent) == 1
    assert pushed(first) is None
    assert pushed(second) == MORNING
    assert PushSubscription.objects.filter(pk=device.pk).exists()


def test_without_a_subject_push_is_off(sent, settings):
    settings.VAPID_SUBJECT = ""
    notification = pending()
    PushSubscriptionFactory(user=notification.recipient)

    send_pending_pushes(MORNING)

    assert sent == []
    assert pushed(notification) is None


def test_one_from_a_farm_the_recipient_no_longer_reaches_is_not_pushed(sent):
    farm = FarmFactory()
    elsewhere = FarmFactory(producer=farm.producer)
    employee = make_delegate(farm.producer, [VIEW], farm=elsewhere)
    notification = NotificationFactory(
        recipient=employee, activity=AgriculturalActivityFactory(plot=PlotFactory(farm=farm))
    )
    Notification.objects.filter(pk=notification.pk).update(created_at=MORNING)
    PushSubscriptionFactory(user=employee)

    send_pending_pushes(MORNING)

    assert sent == []
    assert pushed(notification) is None


def test_one_for_a_recipient_who_cannot_view_activities_is_not_pushed(sent):
    farm = FarmFactory()
    employee = make_delegate(farm.producer, [], farm=farm)
    notification = NotificationFactory(
        recipient=employee, activity=AgriculturalActivityFactory(plot=PlotFactory(farm=farm))
    )
    Notification.objects.filter(pk=notification.pk).update(created_at=MORNING)
    PushSubscriptionFactory(user=employee)

    send_pending_pushes(MORNING)

    assert sent == []
    assert pushed(notification) is None


def test_one_from_a_farm_the_recipient_reaches_is_pushed(sent):
    farm = FarmFactory()
    employee = make_delegate(farm.producer, [VIEW], farm=farm)
    notification = NotificationFactory(
        recipient=employee, activity=AgriculturalActivityFactory(plot=PlotFactory(farm=farm))
    )
    Notification.objects.filter(pk=notification.pk).update(created_at=MORNING)
    PushSubscriptionFactory(user=employee)

    send_pending_pushes(MORNING)

    assert len(sent) == 1


# Los avisos de un lote.


def lot_recipient(lot):
    farm = lot.harvest.plot.farm
    return make_delegate(farm.producer, ["lots.view_lot"], farm=farm)


def test_a_lot_notification_is_pushed_to_whoever_sees_the_lot(sent):
    lot = LotFactory()
    recipient = lot_recipient(lot)
    notification = LotNotificationFactory(lot=lot, recipient=recipient)
    Notification.objects.filter(pk=notification.pk).update(created_at=MORNING)
    PushSubscriptionFactory(user=recipient)

    send_pending_pushes(MORNING)

    ((_, payload),) = sent
    assert payload["title"] == "Volteo pendiente"
    assert payload["url"] == f"/lotes/detalle?id={lot.pk}&notificacion={notification.pk}"


@pytest.fixture
def overdrying():
    """Un sobresecado y un próximo a meta de la misma bitácora, listos para crear, para alguien
    con un dispositivo."""
    entry = DryingLogEntryFactory()
    lot = entry.process.lot
    recipient = lot_recipient(lot)
    PushSubscriptionFactory(user=recipient)

    def draft(kind, severity):
        return NotificationDraft(
            recipient_id=recipient.pk,
            kind=kind,
            severity=severity,
            condition_key=f"{entry.pk}:{kind}",
            thread_key=f"lot:{lot.pk}:{kind}",
            lot_id=lot.pk,
            drying_log_id=entry.pk,
        )

    return [draft("drying_overdried", "critical"), draft("drying_near_target", "normal")]


def at(monkeypatch, instant):
    monkeypatch.setattr(timezone, "now", lambda: instant)


@pytest.fixture
def inline_background(monkeypatch):
    """El envío de fondo corre en el mismo hilo: el hilo de verdad usaría su propia conexión y no
    vería lo que la prueba todavía no confirmó."""
    monkeypatch.setattr(create, "run_in_background", lambda task, *a, where, **kw: task(*a, **kw))


def test_an_overdrying_is_pushed_as_soon_as_it_is_created(
    sent, overdrying, inline_background, django_capture_on_commit_callbacks, monkeypatch
):
    # 20:00 UTC son las 15:00 en Bogotá.
    at(monkeypatch, datetime(2026, 10, 16, 20, 0, tzinfo=UTC))

    with django_capture_on_commit_callbacks(execute=True):
        create_notifications(overdrying)

    ((_, payload),) = sent
    assert payload["title"] == "Sobresecado"
    # Lo que no es crítico espera a la evaluación siguiente.
    assert Notification.objects.get(kind="drying_near_target").pushed_at is None


def test_at_night_an_overdrying_waits_for_the_morning(
    sent, overdrying, inline_background, django_capture_on_commit_callbacks, monkeypatch
):
    # 02:00 UTC son las 21:00 en Bogotá.
    at(monkeypatch, datetime(2026, 10, 17, 2, 0, tzinfo=UTC))

    with django_capture_on_commit_callbacks(execute=True):
        create_notifications(overdrying)

    assert sent == []
    assert Notification.objects.get(kind="drying_overdried").pushed_at is None


def test_the_immediate_push_leaves_the_request_and_waits_for_the_commit(
    sent, overdrying, django_capture_on_commit_callbacks, monkeypatch
):
    at(monkeypatch, datetime(2026, 10, 16, 20, 0, tzinfo=UTC))
    scheduled = []
    monkeypatch.setattr(
        create, "run_in_background", lambda task, *a, where, **kw: scheduled.append((task, a, kw))
    )

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        create_notifications(overdrying)

    # Hasta que la transacción se confirme no se programa nada, y programarlo no envía nada.
    assert scheduled == []
    assert len(callbacks) == 1
    callbacks[0]()
    ((task, args, kwargs),) = scheduled
    assert task is send_pending_pushes
    assert kwargs["notification_ids"] == [Notification.objects.get(kind="drying_overdried").pk]
    assert sent == []

    task(*args, **kwargs)

    assert [payload["title"] for _, payload in sent] == ["Sobresecado"]


def test_one_that_is_not_critical_schedules_nothing(
    overdrying, django_capture_on_commit_callbacks, monkeypatch
):
    scheduled = []
    monkeypatch.setattr(create, "run_in_background", lambda *a, **kw: scheduled.append(a))
    normal = [draft for draft in overdrying if draft.severity != "critical"]

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        create_notifications(normal)

    assert callbacks == []
    assert scheduled == []


def test_a_late_overdrying_is_hidden_and_not_pushed(
    sent, overdrying, inline_background, django_capture_on_commit_callbacks, monkeypatch
):
    at(monkeypatch, datetime(2026, 10, 16, 20, 0, tzinfo=UTC))
    critical = overdrying[0]
    # Una medición más reciente del mismo lote y tipo ya está en la bandeja.
    Notification.objects.create(
        recipient_id=critical.recipient_id,
        kind=critical.kind,
        severity="critical",
        condition_key="newer",
        thread_key=critical.thread_key,
        lot_id=critical.lot_id,
        drying_log=DryingLogEntryFactory(),
        condition_at=datetime(2026, 10, 16, 18, 0, tzinfo=UTC),
    )
    late = replace(critical, condition_at=datetime(2026, 10, 15, 18, 0, tzinfo=UTC))

    with django_capture_on_commit_callbacks(execute=True):
        create_notifications([late])

    assert sent == []
    assert Notification.objects.get(condition_key=late.condition_key).dismissed_at is not None
