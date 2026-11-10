"""Las reglas de bodega que no dependen de la base: se prueban solas."""

from datetime import date
from decimal import Decimal

from .choices import ExitReason

DATE_IN_FUTURE = "La fecha no puede ser futura"
ENTRY_BEFORE_CLASSIFICATION = "La fecha no puede ser anterior a la clasificación"
EXIT_BEFORE_ENTRY = "La fecha no puede ser anterior al ingreso del lote"
DETAIL_REQUIRED = "Describa el motivo de la salida"


def entry_date_errors(entry_date: date, *, today: date, classified_on: date) -> list[str]:
    """El ingreso no es futuro ni anterior al día en que se clasificó el lote."""
    if entry_date > today:
        return [DATE_IN_FUTURE]
    if entry_date < classified_on:
        return [ENTRY_BEFORE_CLASSIFICATION]
    return []


def exit_date_errors(exit_date: date, *, today: date, entered_on: date) -> list[str]:
    """Una salida no es futura ni anterior al ingreso: el cacao no podía salir antes de estar."""
    if exit_date > today:
        return [DATE_IN_FUTURE]
    if exit_date < entered_on:
        return [EXIT_BEFORE_ENTRY]
    return []


def exit_detail_errors(reason: str, detail: str) -> list[str]:
    """Con Otro, el detalle es lo único que dice por qué sale el cacao."""
    if reason == ExitReason.OTHER and not detail.strip():
        return [DETAIL_REQUIRED]
    return []


def remaining(entered_kg: Decimal, exits_kg: Decimal) -> Decimal:
    """Lo que queda de un calibre: lo ingresado menos lo que salió y sigue vigente."""
    return entered_kg - exits_kg


def entry_is_intact(entered: dict[str, Decimal], balances: dict[str, Decimal]) -> bool:
    """Si de un ingreso no ha salido nada: cada calibre con kilos ingresados conserva todos. Solo
    entonces el ingreso se puede corregir, porque nada depende de él."""
    return all(balances.get(grade) == kilos for grade, kilos in entered.items() if kilos > 0)
