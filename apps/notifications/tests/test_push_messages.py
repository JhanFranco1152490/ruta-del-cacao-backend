from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from apps.notifications.push.messages import push_message

TODAY = date(2026, 10, 16)
ASSIGNEE = 7
FOREMAN = 8


def activity(days_from_today=-3, **kwargs):
    fields = {
        "pk": "a1",
        "assignee_id": ASSIGNEE,
        "scheduled_date": TODAY + timedelta(days=days_from_today),
        "activity_type": "pruning",
        "other_description": None,
        "plot": SimpleNamespace(code="P-01", farm=SimpleNamespace(name="La Esperanza")),
        **kwargs,
    }
    fields.setdefault("get_activity_type_display", lambda: "Poda")
    return SimpleNamespace(**fields)


def notification(kind, act=None, detection=None, pk="n1"):
    act = act or activity()
    return SimpleNamespace(
        pk=pk,
        kind=kind,
        activity=act,
        activity_id=act.pk,
        detection=detection,
        thread_key=f"activity:{act.pk}",
    )


def message(notifications, recipient_id=ASSIGNEE):
    return push_message(notifications, recipient_id, TODAY)


def test_the_assignee_reads_that_the_overdue_activity_is_theirs():
    result = message([notification("activity_overdue")])

    assert result["title"] == "Tu actividad está vencida"
    assert result["body"] == "Poda · P-01 · La Esperanza · 3 días de retraso"


def test_someone_else_reads_it_without_your():
    result = message([notification("activity_overdue")], recipient_id=FOREMAN)

    assert result["title"] == "Actividad vencida"


@pytest.mark.parametrize(
    "days, title, ending",
    [
        (-1, "Tu actividad está retrasada", "1 día de retraso"),
        (-2, "Último día para reprogramar tu actividad", "2 días de retraso"),
    ],
)
def test_the_delayed_message_says_the_days(days, title, ending):
    result = message([notification("activity_delayed", activity(days))])

    assert result["title"] == title
    assert result["body"].endswith(ending)


def test_the_last_day_to_reschedule_for_whoever_schedules():
    result = message([notification("activity_delayed", activity(-2))], recipient_id=FOREMAN)

    assert result["title"] == "Último día para reprogramar"


@pytest.mark.parametrize("days, ending", [(2, "Faltan 2 días"), (1, "Es mañana"), (0, "Es hoy")])
def test_the_upcoming_message_says_when(days, ending):
    result = message([notification("activity_upcoming", activity(days))])

    assert result["title"] == "Actividad próxima a su fecha"
    assert result["body"] == f"Poda · P-01 · La Esperanza · {ending}"


def test_other_shows_its_description():
    other = activity(activity_type="other", other_description="Resiembra")

    assert message([notification("activity_overdue", other)])["body"].startswith("Resiembra ·")


def test_a_pending_control_names_the_pest():
    detection = SimpleNamespace(
        pk="d1", pest_disease=SimpleNamespace(name="Monilia"), other_description=None
    )

    result = message(
        [notification("detection_control_pending", detection=detection)], recipient_id=FOREMAN
    )

    assert result["title"] == "Control pendiente"
    assert result["body"] == "Monilia · P-01 · La Esperanza"


def test_a_pending_control_of_other_shows_what_was_written():
    detection = SimpleNamespace(pk="d1", pest_disease=None, other_description="Hormigas en hojas")

    result = message([notification("detection_control_pending", detection=detection)])

    assert result["body"].startswith("Hormigas en hojas ·")


def test_one_notification_opens_its_activity_and_marks_itself_read():
    result = message([notification("activity_overdue")])

    assert result["url"] == "/actividades?mes=2026-10&actividad=a1&notificacion=n1"
    assert result["tag"] == "activity:a1"


def test_several_are_summed_up_in_one():
    result = message(
        [
            notification("activity_upcoming", activity(1), pk="n1"),
            notification("activity_upcoming", activity(2), pk="n2"),
            notification("activity_overdue", pk="n3"),
        ]
    )

    assert result["title"] == "Tienes 3 avisos nuevos"
    assert result["body"] == "2 actividades próximas y 1 vencida"
    assert result["url"] == "/?notificaciones=abiertas"
    assert result["tag"] == "summary"


def test_the_summary_counts_every_kind():
    detection = SimpleNamespace(pk="d1", pest_disease=None, other_description="x")
    result = message(
        [
            notification("activity_delayed", activity(-1), pk="n1"),
            notification("activity_overdue", pk="n2"),
            notification("activity_overdue", pk="n3"),
            notification("detection_control_pending", detection=detection, pk="n4"),
        ]
    )

    assert result["body"] == "1 actividad retrasada, 2 vencidas y 1 control pendiente"


def test_no_name_ever_reaches_the_phone():
    named = activity(assignee=SimpleNamespace(get_full_name=lambda: "Luis Mora"))

    result = message([notification("activity_overdue", named)], recipient_id=FOREMAN)

    assert "Luis" not in str(result)
