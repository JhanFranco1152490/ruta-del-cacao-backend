"""Las reglas de los reportes: cómo se nombra cada cosa y en qué orden van las filas. Funciones
puras, sin consultas."""

from datetime import date
from decimal import Decimal

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.figures import ZERO, code_order, one_decimal


def labeled(code: str, name: str) -> str:
    """Un código con su nombre («F02 · La Esperanza»); sin nombre, solo el código."""
    return f"{code} · {name}" if name else code


def farm_text(place) -> str:
    return labeled(place.farm_code, place.farm_name)


def plot_text(place) -> str:
    return labeled(place.plot_code, place.plot_name)


def producer_text(member_code: str, first_name: str, last_name: str) -> str:
    return labeled(member_code, f"{first_name} {last_name}".strip())


def date_text(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def period_text(period: IndicatorPeriod) -> str:
    return f"{date_text(period.date_from)} – {date_text(period.date_to)}"


def place_order(place) -> tuple:
    """Por finca y luego por parcela, cada código por su número."""
    return code_order(place.farm_code), code_order(place.plot_code)


def kg_sum(values) -> Decimal:
    return one_decimal(sum(values, ZERO))


def reason_text(reason: str, detail: str) -> str:
    """El motivo de un descarte con su detalle, si lo tiene («Otro: Se mojó»)."""
    if reason and detail:
        return f"{reason}: {detail}"
    return reason or detail
