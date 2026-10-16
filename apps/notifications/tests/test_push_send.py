import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from py_vapid import Vapid02
from pywebpush import WebPushException

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.notifications.models import Notification, PushSubscription
from apps.notifications.push import send
from apps.notifications.push.send import send_pending_pushes
from apps.notifications.services.evaluate import evaluate_alerts
from apps.notifications.tests.factories import NotificationFactory, PushSubscriptionFactory

pytestmark = pytest.mark.django_db

# 11:05 UTC son las 6:05 en Bogotá: la primera hora con push.
MORNING = datetime(2026, 10, 16, 11, 5, tzinfo=UTC)


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


@pytest.fixture
def sent(monkeypatch):
    # Nada sale a la red.
    calls = Sent()

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl, timeout):
        endpoint = subscription_info["endpoint"]
        assert vapid_private_key == "privada"
        assert vapid_claims == {"sub": "mailto:equipo@example.com"}
        if endpoint in calls.failures:
            response = SimpleNamespace(status_code=calls.failures[endpoint])
            raise WebPushException("fallo", response=response)
        calls.append((endpoint, json.loads(data)))

    monkeypatch.setattr(send, "webpush", fake_webpush)
    return calls


def pending(recipient=None, created=MORNING, **kwargs):
    notification = NotificationFactory(**({"recipient": recipient} if recipient else {}), **kwargs)
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
    pending(recipient=recipient)
    pending(recipient=recipient)
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
