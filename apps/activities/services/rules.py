"""Las reglas de la planeación de una actividad, comunes a programarla y a editarla."""

from datetime import date

from ..choices import ActivityType
from ..exceptions import (
    ActivityTypeNotAllowed,
    AssigneeNotAvailable,
    FarmInactive,
    InvalidActivity,
    PlotInactive,
)
from ..state import today_in_bogota
from . import queries

DESCRIPTION_MIN = 2
DESCRIPTION_MAX = 80


def ensure_plot_open(plot) -> None:
    # La finca primero: con ella inactiva, sus parcelas quedan congeladas aunque estén activas.
    if not plot.farm.is_active:
        raise FarmInactive()
    if not plot.is_active:
        raise PlotInactive()


def ensure_type_allowed(activity_type: str) -> None:
    if activity_type == ActivityType.PHYTOSANITARY_CONTROL:
        raise ActivityTypeNotAllowed()


def clean_description(activity_type: str, description: str | None) -> str | None:
    """La descripción que se guarda: obligatoria con "Otro" y ausente con cualquier otro tipo."""
    text = (description or "").strip()
    if activity_type != ActivityType.OTHER:
        if text:
            raise InvalidActivity(
                "other_description", "Solo una actividad de tipo Otro lleva descripción."
            )
        return None
    if not DESCRIPTION_MIN <= len(text) <= DESCRIPTION_MAX:
        raise InvalidActivity(
            "other_description",
            f"Indica qué labor es, entre {DESCRIPTION_MIN} y {DESCRIPTION_MAX} caracteres.",
        )
    return text


def ensure_not_past(scheduled_date: date) -> None:
    if scheduled_date < today_in_bogota():
        raise InvalidActivity("scheduled_date", "La fecha debe ser actual o futura.")


def assignee_for(producer_id, account_id):
    account = queries.assignable_account(producer_id, account_id)
    if account is None:
        raise AssigneeNotAvailable()
    return account
