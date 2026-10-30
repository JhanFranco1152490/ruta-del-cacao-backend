from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.common.contracts import alerts
from apps.drying.tests.factories import DryingLogEntryFactory
from apps.fermentation.tests.factories import FermentationTurnFactory
from apps.notifications.choices import NotificationKind
from apps.notifications.models import Notification
from apps.notifications.services.create import create_notifications
from apps.notifications.services.resolve import resolve_notifications, withdraw_notifications
from apps.notifications.tests.factories import LotNotificationFactory

pytestmark = pytest.mark.django_db

TURN_DUE = NotificationKind.FERMENTATION_TURN_DUE
FIRST_TURN = NotificationKind.FERMENTATION_FIRST_TURN_DUE
LOG_DUE = NotificationKind.DRYING_LOG_DUE


# Resolver lo que faltaba.


def test_resolving_marks_the_pending_ones_of_the_lot():
    pending = LotNotificationFactory()
    reminder = LotNotificationFactory(lot=pending.lot, kind=FIRST_TURN, condition_key="r")

    resolved = resolve_notifications(pending.lot_id, [TURN_DUE, FIRST_TURN])

    assert resolved == 2
    pending.refresh_from_db()
    reminder.refresh_from_db()
    assert pending.resolved_at is not None
    assert reminder.resolved_at is not None


def test_resolving_keeps_when_an_earlier_one_was_resolved():
    earlier = timezone.now() - timedelta(days=1)
    notification = LotNotificationFactory(resolved_at=earlier)

    assert resolve_notifications(notification.lot_id, [TURN_DUE]) == 0
    notification.refresh_from_db()
    assert notification.resolved_at == earlier


def test_resolving_leaves_other_lots_and_other_kinds_alone():
    notification = LotNotificationFactory()
    other_lot = LotNotificationFactory()
    log_due = LotNotificationFactory(lot=notification.lot, kind=LOG_DUE, condition_key="d")

    resolve_notifications(notification.lot_id, [TURN_DUE])

    other_lot.refresh_from_db()
    log_due.refresh_from_db()
    assert other_lot.resolved_at is None
    assert log_due.resolved_at is None


# Retirar los desvíos que ya no se cumplen.


def deviation(record, kind, **fields):
    lot = record.process.lot
    return LotNotificationFactory(
        lot=lot, kind=kind, condition_key=f"{record.pk}:{kind}", **fields
    )


def test_withdrawing_deletes_only_the_kinds_asked_for():
    turn = FermentationTurnFactory()
    gone = deviation(turn, NotificationKind.FERMENTATION_TEMPERATURE_HIGH, fermentation_turn=turn)
    kept = deviation(turn, NotificationKind.FERMENTATION_PH_LOW, fermentation_turn=turn)

    deleted = withdraw_notifications(
        [NotificationKind.FERMENTATION_TEMPERATURE_HIGH], fermentation_turn_id=turn.pk
    )

    assert deleted == 1
    assert not Notification.objects.filter(pk=gone.pk).exists()
    assert Notification.objects.filter(pk=kept.pk).exists()


def test_withdrawing_leaves_the_deviations_of_another_record():
    entry, other = DryingLogEntryFactory(), DryingLogEntryFactory()
    deviation(entry, NotificationKind.DRYING_OVERDRIED, drying_log=entry)
    kept = deviation(other, NotificationKind.DRYING_OVERDRIED, drying_log=other)

    withdraw_notifications([NotificationKind.DRYING_OVERDRIED], drying_log_id=entry.pk)

    assert list(Notification.objects.all()) == [kept]


def test_a_withdrawn_deviation_can_be_notified_again():
    # Borrar la fila, y no solo ocultarla, es lo que deja avisar otra vez si una corrección vuelve
    # a cumplir la condición: una fila oculta seguiría contando como ya avisada.
    entry = DryingLogEntryFactory()
    first = deviation(entry, NotificationKind.DRYING_OVERDRIED, drying_log=entry)
    withdraw_notifications([NotificationKind.DRYING_OVERDRIED], drying_log_id=entry.pk)

    draft = alerts.NotificationDraft(
        recipient_id=first.recipient_id,
        kind=NotificationKind.DRYING_OVERDRIED,
        condition_key=first.condition_key,
        thread_key=first.thread_key,
        lot_id=first.lot_id,
        drying_log_id=entry.pk,
    )

    assert create_notifications([draft]) == 1


# Por el contrato.


def test_notifications_registers_its_three_operations():
    assert alerts._sink.create is create_notifications
    assert alerts._sink.resolve is resolve_notifications
    assert alerts._sink.withdraw is withdraw_notifications


def test_nothing_happens_if_the_transaction_rolls_back(django_capture_on_commit_callbacks):
    notification = LotNotificationFactory()

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            alerts.resolve(notification.lot_id, [TURN_DUE])
            raise RuntimeError("se revierte")

    notification.refresh_from_db()
    assert notification.resolved_at is None


def test_it_resolves_once_the_transaction_commits(django_capture_on_commit_callbacks):
    notification = LotNotificationFactory()

    with django_capture_on_commit_callbacks(execute=True):
        alerts.resolve(notification.lot_id, [TURN_DUE])

    notification.refresh_from_db()
    assert notification.resolved_at is not None
