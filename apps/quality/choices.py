from django.db import models


class DiscardReason(models.TextChoices):
    """Por qué se descarta cacao, en parte al clasificar o el lote completo. Una lista fija para
    poder contar los descartes por motivo; lo que no cabe va en Otro, con su detalle."""

    MOLD = "mold", "Moho"
    UNDER_FERMENTED = "under_fermented", "Fermentación insuficiente"
    OVER_FERMENTED = "over_fermented", "Sobrefermentado"
    INSECT_DAMAGE = "insect_damage", "Daño por insectos"
    CONTAMINATION = "contamination", "Contaminación (humo, olores, químicos)"
    OTHER = "other", "Otro"
