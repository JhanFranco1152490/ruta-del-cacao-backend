from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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


# Los avisos de un lote.

LOT_CODE = "000123-F02-P05-261014-1"


def lot_notification(kind, pk="n9", **fields):
    lot = SimpleNamespace(
        pk="l1",
        code=LOT_CODE,
        harvest=SimpleNamespace(plot=SimpleNamespace(farm=SimpleNamespace(name="La Esperanza"))),
    )
    return SimpleNamespace(
        pk=pk,
        kind=kind,
        activity=None,
        lot=lot,
        fermentation_turn=fields.pop("turn", None),
        drying_log=fields.pop("log", None),
        condition_at=fields.pop("condition_at", None),
        thread_key=f"lot:l1:{kind}",
        **fields,
    )


def test_a_lot_notification_opens_the_lot_and_marks_itself_read():
    result = message([lot_notification("drying_log_due")])

    assert result["url"] == "/lotes/detalle?id=l1&notificacion=n9"
    assert result["tag"] == "lot:l1:drying_log_due"
    assert result["title"] == "Bitácora de secado pendiente"
    assert result["body"] == f"{LOT_CODE} · La Esperanza · Falta la bitácora del día"


def test_a_pending_turn_says_its_hour_in_bogota():
    # 19:00 UTC son las 14:00 en Bogotá.
    at = datetime(2026, 10, 16, 19, 0, tzinfo=UTC)

    reminder = message([lot_notification("fermentation_first_turn_due", condition_at=at)])
    pending = message([lot_notification("fermentation_turn_due", condition_at=at)])

    assert reminder["title"] == "Se acerca el primer volteo"
    assert reminder["body"] == f"{LOT_CODE} · La Esperanza · A las 14:00"
    assert pending["title"] == "Volteo pendiente"
    assert pending["body"] == f"{LOT_CODE} · La Esperanza · Desde las 14:00"


@pytest.mark.parametrize(
    ("kind", "title"),
    [
        ("drying_slow_stalled", "Secado lento – riesgo de hongo"),
        ("drying_slow_duration", "Secado lento – riesgo de hongo"),
        ("drying_accelerated", "Secado acelerado – riesgo de daño físico"),
        ("drying_near_target", "Próximo a meta – preparar ensacado"),
        ("drying_overdried", "Sobresecado"),
    ],
)
def test_a_drying_deviation_says_the_moisture_with_a_decimal_comma(kind, title):
    log = SimpleNamespace(moisture_pct=Decimal("5.8"))

    result = message([lot_notification(kind, log=log)])

    assert result["title"] == title
    assert result["body"] == f"{LOT_CODE} · La Esperanza · Humedad 5,8 %"


@pytest.mark.parametrize(
    ("kind", "title", "detail"),
    [
        ("fermentation_temperature_low", "Temperatura por debajo del rango", "37,5 °C"),
        ("fermentation_temperature_high", "Temperatura por encima del rango", "37,5 °C"),
        ("fermentation_ph_low", "Grano demasiado ácido", "pH 3,90"),
        ("fermentation_ph_high", "La fermentación no avanza", "pH 3,90"),
    ],
)
def test_a_fermentation_deviation_says_what_was_measured(kind, title, detail):
    turn = SimpleNamespace(temperature_c=Decimal("37.5"), ph=Decimal("3.90"))

    result = message([lot_notification(kind, turn=turn)])

    assert result["title"] == title
    assert result["body"] == f"{LOT_CODE} · La Esperanza · {detail}"


def test_the_summary_counts_postharvest_records_and_deviations():
    log = SimpleNamespace(moisture_pct=Decimal("5.8"))
    result = message(
        [
            notification("activity_overdue", pk="n1"),
            lot_notification("fermentation_turn_due", pk="n2"),
            lot_notification("drying_log_due", pk="n3"),
            lot_notification("drying_overdried", pk="n4", log=log),
        ]
    )

    assert result["body"] == (
        "1 actividad vencida, 2 registros de poscosecha pendientes y 1 desvío de poscosecha"
    )


def test_a_single_postharvest_part_reads_well():
    log = SimpleNamespace(moisture_pct=Decimal("8.1"))
    result = message(
        [
            lot_notification("drying_near_target", pk="n1", log=log),
            lot_notification("drying_overdried", pk="n2", log=log),
        ]
    )

    assert result["body"] == "2 desvíos de poscosecha"
