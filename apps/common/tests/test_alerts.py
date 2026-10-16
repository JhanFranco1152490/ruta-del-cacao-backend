from datetime import date

import pytest

from apps.common import alerts
from apps.common.alerts import NotificationDraft


@pytest.fixture
def empty_registry(monkeypatch):
    monkeypatch.setattr(alerts, "_evaluators", {})
    monkeypatch.setattr(alerts, "_sink", None)


def draft(**kwargs):
    return NotificationDraft(
        recipient_id=1,
        kind="activity_overdue",
        condition_key="a",
        thread_key="activity:a",
        **kwargs,
    )


def test_a_draft_is_normal_by_default():
    assert draft().severity == "normal"
    assert draft().activity_id is None


def test_evaluators_are_registered_by_name(empty_registry):
    def first(today):
        return []

    def second(today):
        return []

    alerts.register_evaluator("activities", first)
    alerts.register_evaluator("health", second)
    # Volver a cargar un módulo reemplaza su evaluador en vez de duplicarlo.
    alerts.register_evaluator("activities", second)

    assert alerts.evaluators() == {"activities": second, "health": second}


def test_an_evaluator_only_computes(empty_registry):
    alerts.register_evaluator("activities", lambda today: [draft(condition_date=today)])

    (drafts,) = [list(fn(date(2026, 10, 16))) for fn in alerts.evaluators().values()]

    assert drafts == [draft(condition_date=date(2026, 10, 16))]


@pytest.mark.django_db
def test_notify_writes_only_when_the_transaction_commits(
    empty_registry, django_capture_on_commit_callbacks
):
    received = []
    alerts.register_sink(received.extend)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        alerts.notify([draft()])

    assert received == []
    callbacks[0]()
    assert received == [draft()]


@pytest.mark.django_db
def test_notify_without_a_sink_fails_loudly(empty_registry, django_capture_on_commit_callbacks):
    with pytest.raises(RuntimeError), django_capture_on_commit_callbacks(execute=True):
        alerts.notify([draft()])
