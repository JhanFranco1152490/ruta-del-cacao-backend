from django.db import models

# Las opciones son pocas y estables, y los avisos de coherencia de la ficha dependen de ellas:
# por eso van en el código y no en tablas administrables.


class Stage(models.TextChoices):
    """Etapas del ciclo productivo del cacao: formación, producción y renovación."""

    ESTABLISHMENT = "establishment", "Establecimiento o formación"
    EARLY_PRODUCTION = "early_production", "Inicio de producción"
    FULL_PRODUCTION = "full_production", "Producción estable"
    RENOVATION = "renovation", "Renovación o rehabilitación"


class ManagementSystem(models.TextChoices):
    # El criterio que importa para vender: el cacao orgánico se comercializa distinto.
    CONVENTIONAL = "conventional", "Convencional"
    ORGANIC = "organic", "Orgánico"
    IN_TRANSITION = "in_transition", "En transición a orgánico"


class ShadeType(models.TextChoices):
    NONE = "none", "A plena exposición"
    TEMPORARY = "temporary", "Sombra temporal"
    PERMANENT = "permanent", "Sombra permanente"
    MIXED = "mixed", "Temporal y permanente"
