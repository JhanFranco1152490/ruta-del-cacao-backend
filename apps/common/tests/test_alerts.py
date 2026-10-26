from datetime import date

import pytest

from apps.common.contracts import alerts
from apps.common.contracts.alerts import NotificationDraft


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


@pytest.fixture
def recorded(empty_registry):
    """Un sink que solo anota qué le pidieron."""
    calls = []
    alerts.register_sink(
        alerts.NotificationSink(
            create=lambda drafts: calls.append(("create", drafts)),
            resolve=lambda lot_id, kinds: calls.append(("resolve", lot_id, kinds)),
            withdraw=lambda kinds, **record: calls.append(("withdraw", kinds, record)),
        )
    )
    return calls


@pytest.mark.django_db
def test_notify_writes_only_when_the_transaction_commits(
    recorded, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        alerts.notify([draft()])

    assert recorded == []
    callbacks[0]()
    assert recorded == [("create", [draft()])]


@pytest.mark.django_db
def test_resolve_runs_only_when_the_transaction_commits(
    recorded, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        alerts.resolve("lot-1", ["fermentation_turn_due"])

    assert recorded == []
    callbacks[0]()
    assert recorded == [("resolve", "lot-1", ["fermentation_turn_due"])]


@pytest.mark.django_db
def test_withdraw_runs_only_when_the_transaction_commits(
    recorded, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        alerts.withdraw(["drying_overdried"], drying_log_id="log-1")

    assert recorded == []
    callbacks[0]()
    assert recorded == [("withdraw", ["drying_overdried"], {"drying_log_id": "log-1"})]


@pytest.mark.parametrize("record", [{}, {"fermentation_turn_id": "t", "drying_log_id": "d"}])
def test_withdraw_names_exactly_one_record(recorded, record):
    # Sin registro borraría los desvíos de todos; con dos, no se sabe de cuál.
    with pytest.raises(ValueError):
        alerts.withdraw(["drying_overdried"], **record)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "call",
    [
        lambda: alerts.notify([draft()]),
        lambda: alerts.resolve("lot-1", ["fermentation_turn_due"]),
        lambda: alerts.withdraw(["drying_overdried"], drying_log_id="log-1"),
    ],
)
def test_without_a_sink_it_fails_loudly(empty_registry, django_capture_on_commit_callbacks, call):
    with pytest.raises(RuntimeError), django_capture_on_commit_callbacks(execute=True):
        call()
