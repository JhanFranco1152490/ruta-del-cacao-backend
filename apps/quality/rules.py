"""Las reglas de calidad que no dependen de la base: se prueban solas."""

from decimal import Decimal

from .choices import DiscardReason
from .exceptions import ClassificationSumMismatch, QualitySumExceeds100
from .models import MAX_PERCENT

REASON_REQUIRED = "Indique el motivo del descarte"
REASON_WITHOUT_DISCARD = "Sin descarte no hay motivo"
DETAIL_REQUIRED = "Describa el motivo del descarte"


def percentages_total(well_fermented: Decimal, moldy: Decimal, other_defects: Decimal) -> Decimal:
    return well_fermented + moldy + other_defects


def check_percentages_total(well_fermented: Decimal, moldy: Decimal, other_defects: Decimal):
    """Los tres porcentajes son partes de la misma muestra: juntos no pasan de 100. El resto son
    granos que no caen en ninguna de las tres (violetas, pizarrosos)."""
    total = percentages_total(well_fermented, moldy, other_defects)
    if total > MAX_PERCENT:
        raise QualitySumExceeds100(total)


def _kilos(value: Decimal) -> str:
    return f"{abs(value):.1f}".replace(".", ",")


def difference_message(difference: Decimal) -> str:
    """Lo que falta o sobra para llegar al peso seco, como lo lee quien clasifica."""
    if difference > 0:
        return f"Faltan {_kilos(difference)} kg por distribuir"
    return f"Sobran {_kilos(difference)} kg"


def check_classification_total(dry_weight: Decimal, g1: Decimal, g2: Decimal, discard: Decimal):
    """G1, G2 y descarte deben sumar exactamente el peso seco del lote."""
    received = g1 + g2 + discard
    difference = dry_weight - received
    if difference != 0:
        raise ClassificationSumMismatch(
            difference_message(difference),
            expected_kg=dry_weight,
            received_kg=received,
            difference_kg=difference,
        )


def discard_reason_errors(discard_kg: Decimal, reason: str, detail: str) -> dict:
    """Los errores del motivo de un descarte parcial: con kilos de descarte va el motivo, sin ellos
    no, y con Otro también su detalle."""
    if discard_kg > 0 and not reason:
        return {"discard_reason": [REASON_REQUIRED]}
    if discard_kg == 0 and reason:
        return {"discard_reason": [REASON_WITHOUT_DISCARD]}
    if reason == DiscardReason.OTHER and not detail.strip():
        return {"discard_detail": [DETAIL_REQUIRED]}
    return {}
