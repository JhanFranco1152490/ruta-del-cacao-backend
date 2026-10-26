import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.common.contracts import alerts
from apps.common.contracts.alerts import NotificationDraft
from apps.health.tests.factories import DetectionFactory, PhytosanitaryTreatmentFactory
from apps.notifications.models import Notification
from apps.notifications.services.evaluate import evaluate_alerts, evaluation_date
from apps.notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 16, 11, 5, tzinfo=UTC)


def overdue_activity(**kwargs):
    return AgriculturalActivityFactory(scheduled_date=TODAY - timedelta(days=3), **kwargs)


# La fecha de la evaluación.


def test_the_day_starts_at_midnight_in_bogota_not_in_utc():
    # 00:05 en Bogotá son las 05:05 UTC: ahí empieza el día nuevo.
    assert evaluation_date(datetime(2026, 10, 16, 5, 5, tzinfo=UTC)) == date(2026, 10, 16)
    assert evaluation_date(datetime(2026, 10, 16, 4, 55, tzinfo=UTC)) == date(2026, 10, 15)


# Evaluar.


def test_it_creates_what_the_evaluators_find():
    activity = overdue_activity()

    result = evaluate_alerts(TODAY, NOW)

    assert result.created["activities"] == 1
    assert result.failed == []
    assert Notification.objects.get().recipient == activity.assignee


def test_evaluating_again_creates_nothing_new():
    overdue_activity()
    evaluate_alerts(TODAY, NOW)

    result = evaluate_alerts(TODAY, NOW)

    assert result.created["activities"] == 0
    assert Notification.objects.count() == 1


@pytest.fixture
def failing_evaluator(monkeypatch):
    activity = overdue_activity(assignee=UserFactory(first_name="Luis", last_name="Mora"))
    draft = NotificationDraft(
        recipient_id=activity.assignee_id,
        kind="activity_overdue",
        condition_key="ok",
        thread_key=f"activity:{activity.pk}",
        activity_id=activity.pk,
    )

    # El dato llega en una variable, como llegaría de la base: el traceback muestra la línea
    # de código, y en código real nunca hay datos personales escritos.
    message = f"{activity.assignee.get_full_name()}, documento 1090123456"

    def broken(today, now):
        raise ValueError(message)

    monkeypatch.setattr(
        alerts, "_evaluators", {"broken": broken, "working": lambda today, now: [draft]}
    )


@pytest.fixture
def received(monkeypatch):
    """Un evaluador que solo anota con qué día y qué hora lo llamaron."""
    calls = []

    def recording(today, now):
        calls.append((today, now))
        return []

    monkeypatch.setattr(alerts, "_evaluators", {"recording": recording})
    return calls


def test_each_evaluator_receives_the_day_and_the_time(received):
    evaluate_alerts(TODAY, NOW)

    assert received == [(TODAY, NOW)]


def test_a_failing_evaluator_does_not_stop_the_others(failing_evaluator):
    result = evaluate_alerts(TODAY, NOW)

    assert result.failed == ["broken"]
    assert result.created == {"working": 1}
    assert Notification.objects.filter(condition_key="ok").exists()


def test_the_failure_is_logged_without_its_message(failing_evaluator, caplog):
    with caplog.at_level(logging.ERROR):
        evaluate_alerts(TODAY, NOW)

    assert "broken" in caplog.text
    assert "ValueError" in caplog.text
    assert "Luis Mora" not in caplog.text
    assert "1090123456" not in caplog.text


def test_a_failure_ends_the_command_with_an_error(failing_evaluator):
    with pytest.raises(CommandError):
        call_command("evaluate_alerts", "--today", "2026-10-16")

    assert Notification.objects.filter(condition_key="ok").exists()


# Purgar lo viejo que ya no sirve.


def old(notification, days=91):
    Notification.objects.filter(pk=notification.pk).update(created_at=NOW - timedelta(days=days))
    return notification


def remains(notification):
    return Notification.objects.filter(pk=notification.pk).exists()


def mark_done(activity):
    type(activity).objects.filter(pk=activity.pk).update(
        status=ActivityStatus.DONE, done_date=TODAY, completed_at=NOW
    )


def test_an_old_read_notification_of_a_done_activity_is_purged():
    notification = old(NotificationFactory(read_at=NOW))
    mark_done(notification.activity)

    assert evaluate_alerts(TODAY, NOW).purged == 1
    assert not remains(notification)


def test_an_old_dismissed_notification_of_a_rescheduled_activity_is_purged():
    notification = old(NotificationFactory(dismissed_at=NOW))
    activity = notification.activity
    activity.scheduled_date = TODAY + timedelta(days=20)
    activity.save()

    evaluate_alerts(TODAY, NOW)

    assert not remains(notification)


def test_an_unread_notification_is_kept_however_old():
    notification = old(NotificationFactory(), days=400)
    mark_done(notification.activity)

    evaluate_alerts(TODAY, NOW)

    assert remains(notification)


def test_a_dismissed_overdue_that_is_still_pending_is_kept():
    # Si se borrara, la siguiente evaluación vería la actividad vencida y avisaría de nuevo.
    notification = old(NotificationFactory(dismissed_at=NOW), days=100)

    evaluate_alerts(TODAY, NOW)

    assert remains(notification)
    assert evaluate_alerts(TODAY, NOW).created["activities"] == 0


def test_a_recent_read_notification_of_a_done_activity_is_kept():
    notification = old(NotificationFactory(read_at=NOW), days=89)
    mark_done(notification.activity)

    evaluate_alerts(TODAY, NOW)

    assert remains(notification)


# El comando.


def test_the_command_evaluates_the_given_day(capsys):
    activity = overdue_activity(assignee=UserFactory(first_name="Luis", last_name="Mora"))

    call_command("evaluate_alerts", "--today", "2026-10-16")

    assert Notification.objects.get().activity == activity
    output = capsys.readouterr().out
    assert "activities: 1" in output
    assert "Luis" not in output
    assert activity.assignee.email not in output


@pytest.fixture
def frozen_now(monkeypatch):
    # 20:30 UTC son las 15:30 en Bogotá.
    instant = datetime(2026, 10, 20, 20, 30, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: instant)
    return instant


def test_the_command_passes_the_current_time(received, frozen_now):
    call_command("evaluate_alerts")

    assert received == [(date(2026, 10, 20), frozen_now)]


def test_with_a_given_day_the_time_is_that_day_at_the_current_bogota_hour(received, frozen_now):
    # Las alertas que cuentan horas ven el día pedido como si fuera la hora de ahora.
    call_command("evaluate_alerts", "--today", "2026-10-16")

    ((today, now),) = received
    assert today == date(2026, 10, 16)
    assert timezone.localtime(now) == datetime(
        2026, 10, 16, 15, 30, tzinfo=timezone.get_current_timezone()
    )


def test_the_command_rejects_a_malformed_date():
    with pytest.raises(CommandError):
        call_command("evaluate_alerts", "--today", "16/10/2026")


# El control pendiente: su monitoreo siempre está realizado, cuenta la detección.


def control_pending(**detection_fields):
    detection = DetectionFactory(**detection_fields)
    activity = detection.monitoring.activity
    return NotificationFactory(
        activity=activity,
        detection=detection,
        kind="detection_control_pending",
        condition_key=f"{detection.pk}:0",
        thread_key=f"detection:{detection.pk}",
        condition_date=None,
        read_at=NOW,
    )


def test_an_old_pending_control_that_is_still_pending_is_kept():
    notification = old(control_pending())

    evaluate_alerts(TODAY, NOW)

    assert remains(notification)


def test_an_old_pending_control_that_needs_no_control_anymore_is_purged():
    notification = old(control_pending(control_dismissed_at=NOW))

    evaluate_alerts(TODAY, NOW)

    assert not remains(notification)


def test_an_old_pending_control_that_got_a_control_is_purged():
    notification = old(control_pending())
    PhytosanitaryTreatmentFactory(detection=notification.detection)

    evaluate_alerts(TODAY, NOW)

    assert not remains(notification)
