from django.db import models


class LotStatus(models.TextChoices):
    """Los estados de un lote, en el orden del proceso. Cada módulo mueve el lote con
    `advance_lot_status`; bodega y venta agregan sus estados después de Clasificado."""

    GENERATED = "generated", "Generado"
    FERMENTING = "fermenting", "En fermentación"
    FERMENTED = "fermented", "Fermentado"
    DRYING = "drying", "En secado"
    DRIED = "dried", "Seco"
    EVALUATED = "evaluated", "Evaluado"
    CLASSIFIED = "classified", "Clasificado"
    DISCARDED = "discarded", "Descartado"


# A qué estados puede pasar cada uno. Es una cadena salvo en Evaluado, que se abre en dos: el lote
# se clasifica por calibre o se descarta completo, y desde ahí ya no cambia.
TRANSITIONS: dict[str, frozenset[str]] = {
    LotStatus.GENERATED: frozenset({LotStatus.FERMENTING}),
    LotStatus.FERMENTING: frozenset({LotStatus.FERMENTED}),
    LotStatus.FERMENTED: frozenset({LotStatus.DRYING}),
    LotStatus.DRYING: frozenset({LotStatus.DRIED}),
    LotStatus.DRIED: frozenset({LotStatus.EVALUATED}),
    LotStatus.EVALUATED: frozenset({LotStatus.CLASSIFIED, LotStatus.DISCARDED}),
    LotStatus.CLASSIFIED: frozenset(),
    LotStatus.DISCARDED: frozenset(),
}


def allowed_next(status: str) -> frozenset[str]:
    """Los estados a los que puede pasar un lote que está en `status`."""
    return TRANSITIONS[LotStatus(status)]
