from django.db import models


class Grade(models.TextChoices):
    """El calibre del cacao seco clasificado. Los mismos dos de la clasificación del lote."""

    G1 = "g1", "G1"
    G2 = "g2", "G2"


class ExitReason(models.TextChoices):
    """Por qué sale cacao de la bodega. Una lista fija para poder contar las salidas por motivo; lo
    que no cabe va en Otro, con su detalle. Venta la genera la venta y no se elige a mano."""

    SHRINKAGE = "shrinkage", "Merma"
    SAMPLE = "sample", "Muestra"
    REPROCESSING = "reprocessing", "Reproceso"
    TRANSFER = "transfer", "Traslado fuera de la finca"
    OTHER = "other", "Otro"
    SALE = "sale", "Venta"


# Los que una persona puede elegir al registrar una salida.
MANUAL_EXIT_REASONS = tuple(reason.value for reason in ExitReason if reason is not ExitReason.SALE)
