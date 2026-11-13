"""Lo producido, clasificado y vendido por cada finca, a partir de las fuentes de indicadores.

El panel y los reportes de la asociación muestran las mismas cifras por finca: las arman aquí, con
las mismas filas, para que nunca den números distintos para el mismo periodo.
"""

from dataclasses import dataclass, fields
from decimal import Decimal

from .figures import ZERO


@dataclass(frozen=True)
class FarmFigures:
    green_kg: Decimal = ZERO
    dry_kg: Decimal = ZERO
    # Lo que pesaban en baba las cosechas que ya terminaron de secarse.
    dried_green_kg: Decimal = ZERO
    g1_kg: Decimal = ZERO
    g2_kg: Decimal = ZERO
    discard_kg: Decimal = ZERO
    lots_classified: int = 0
    lots_discarded: int = 0
    sold_g1_kg: Decimal = ZERO
    sold_g2_kg: Decimal = ZERO
    sales: int = 0

    @property
    def green_kg_not_dried(self) -> Decimal:
        return self.green_kg - self.dried_green_kg

    @property
    def sold_kg(self) -> Decimal:
        return self.sold_g1_kg + self.sold_g2_kg


_EMPTY = {field.name: field.default for field in fields(FarmFigures)}


def figures_by_farm(*, harvested, dried, quality, sales) -> dict:
    """Solo las fincas que aparecen en alguna fuente; las demás cifras de cada una, en 0."""
    farms: dict = {}

    def add(farm_id, **values):
        farm = farms.setdefault(farm_id, dict(_EMPTY))
        for name, value in values.items():
            farm[name] += value

    for row in harvested:
        add(row.farm_id, green_kg=row.kg)
    for row in dried:
        add(row.farm_id, dry_kg=row.dry_kg, dried_green_kg=row.green_kg)
    for row in quality:
        add(
            row.farm_id,
            g1_kg=row.g1_kg,
            g2_kg=row.g2_kg,
            discard_kg=row.discard_kg,
            lots_classified=row.lots_classified,
            lots_discarded=row.lots_discarded,
        )
    for row in sales:
        add(row.farm_id, sold_g1_kg=row.g1_kg, sold_g2_kg=row.g2_kg, sales=row.sales)
    return {farm_id: FarmFigures(**values) for farm_id, values in farms.items()}
