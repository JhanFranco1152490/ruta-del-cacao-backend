"""Lo que dice una push: título, una línea, a dónde lleva y su etiqueta.

Nunca lleva nombres de personas ni otro dato personal: viaja por el servicio de push del
navegador y se ve con el teléfono bloqueado. Basta con la labor o la plaga, la parcela y la finca.
"""

from ..choices import NotificationKind

# El tipo "Otro" lleva su descripción en vez del nombre del tipo.
OTHER_TYPE = "other"
# Al tocar una push que resume varios avisos se abre el panel de notificaciones.
SUMMARY_URL = "/?notificaciones=abiertas"
SUMMARY_TAG = "summary"


def push_message(notifications, recipient_id, today) -> dict:
    """La push de una persona en una evaluación: el aviso, si es uno, o un resumen."""
    if len(notifications) == 1:
        return _single(notifications[0], recipient_id, today)
    return {
        "title": f"Tienes {len(notifications)} avisos nuevos",
        "body": _summary(notifications),
        "url": SUMMARY_URL,
        "tag": SUMMARY_TAG,
    }


def _single(notification, recipient_id, today) -> dict:
    activity = notification.activity
    where = f"{activity.plot.code} · {activity.plot.farm.name}"
    if notification.kind == NotificationKind.DETECTION_CONTROL_PENDING:
        title, body = "Control pendiente", f"{_pest(notification.detection)} · {where}"
    else:
        own = recipient_id == activity.assignee_id
        title, when = _activity_title(notification.kind, activity, own, today)
        body = f"{_labor(activity)} · {where} · {when}"
    month = activity.scheduled_date.strftime("%Y-%m")
    return {
        "title": title,
        "body": body,
        "url": f"/actividades?mes={month}&actividad={activity.pk}&notificacion={notification.pk}",
        "tag": notification.thread_key,
    }


def _activity_title(kind, activity, own, today) -> tuple[str, str]:
    if kind == NotificationKind.ACTIVITY_UPCOMING:
        days = (activity.scheduled_date - today).days
        when = {0: "Es hoy", 1: "Es mañana"}.get(days, f"Faltan {days} días")
        return "Actividad próxima a su fecha", when
    days_late = (today - activity.scheduled_date).days
    when = f"{days_late} día de retraso" if days_late == 1 else f"{days_late} días de retraso"
    if kind == NotificationKind.ACTIVITY_OVERDUE:
        return ("Tu actividad está vencida" if own else "Actividad vencida"), when
    if days_late >= 2:
        # El segundo día de retraso es el último en que se puede mover la fecha.
        title = (
            "Último día para reprogramar tu actividad" if own else "Último día para reprogramar"
        )
        return title, when
    return ("Tu actividad está retrasada" if own else "Actividad retrasada"), when


def _labor(activity) -> str:
    if activity.activity_type == OTHER_TYPE:
        return activity.other_description
    return activity.get_activity_type_display()


def _pest(detection) -> str:
    if detection.pest_disease is not None:
        return detection.pest_disease.name
    return detection.other_description


# Cada tipo en el resumen: singular y plural. Las de actividades nombran "actividad" solo en la
# primera parte ("2 actividades próximas y 1 vencida").
_ACTIVITY_PARTS = (
    (NotificationKind.ACTIVITY_UPCOMING, "próxima", "próximas"),
    (NotificationKind.ACTIVITY_DELAYED, "retrasada", "retrasadas"),
    (NotificationKind.ACTIVITY_OVERDUE, "vencida", "vencidas"),
)


def _summary(notifications) -> str:
    counts: dict = {}
    for notification in notifications:
        counts[notification.kind] = counts.get(notification.kind, 0) + 1
    parts = []
    for kind, one, many in _ACTIVITY_PARTS:
        count = counts.get(kind, 0)
        if not count:
            continue
        adjective = one if count == 1 else many
        if not parts:
            adjective = f"{'actividad' if count == 1 else 'actividades'} {adjective}"
        parts.append(f"{count} {adjective}")
    pending = counts.get(NotificationKind.DETECTION_CONTROL_PENDING, 0)
    if pending:
        parts.append(
            f"{pending} control pendiente" if pending == 1 else f"{pending} controles pendientes"
        )
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} y {parts[-1]}"
