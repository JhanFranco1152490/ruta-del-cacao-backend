from django.db import models


class LotStatus(models.TextChoices):
    """La cadena de estados de un lote, en orden. Cada módulo mueve el lote al siguiente estado
    con `advance_lot_status`; calidad, bodega y venta agregan sus estados después de Seco."""

    GENERATED = "generated", "Generado"
    FERMENTING = "fermenting", "En fermentación"
    FERMENTED = "fermented", "Fermentado"
    DRYING = "drying", "En secado"
    DRIED = "dried", "Seco"


_CHAIN = list(LotStatus)


def next_status(status: str) -> str | None:
    """El estado que sigue a `status`, o `None` si es el último de la cadena."""
    position = _CHAIN.index(LotStatus(status))
    return _CHAIN[position + 1].value if position + 1 < len(_CHAIN) else None
