"""Las reglas de una venta que no dependen de la base: se prueban solas."""

from decimal import ROUND_HALF_UP, Decimal


def line_subtotal(quantity_kg: Decimal, price_per_kg: int) -> int:
    """Kilos por precio, en pesos enteros: la mitad sube al peso siguiente. El frontend usa la
    misma regla para mostrar el total mientras se escribe."""
    return int((quantity_kg * price_per_kg).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
