"""Las cuentas propias de los paneles: funciones puras sobre `Decimal`, sin consultas. Las que
comparten con los reportes (redondeo, porcentajes, orden de códigos) están en
`apps.common.figures`."""

from decimal import Decimal

from apps.common.figures import ZERO, one_decimal


def per_hectare(kg: Decimal, area_hectares: Decimal) -> Decimal | None:
    """Sin área no hay rendimiento por hectárea: `None`, no 0."""
    if not area_hectares:
        return None
    return one_decimal(kg / area_hectares)


def month_series(months: list[str], values: dict[str, dict], keys: tuple[str, ...]) -> list[dict]:
    """Una fila por cada mes del periodo, también sin datos (en 0), para que un gráfico no salte
    meses."""
    return [
        {
            "month": month,
            **{key: one_decimal(values.get(month, {}).get(key, ZERO)) for key in keys},
        }
        for month in months
    ]
