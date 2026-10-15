from django.db import models


class PestDiseaseKind(models.TextChoices):
    PEST = "pest", "Plaga"
    DISEASE = "disease", "Enfermedad"


class SamplingUnit(models.TextChoices):
    """Qué contó el capataz. Un 24 % de árboles no es lo mismo que un 24 % de mazorcas."""

    TREES = "trees", "Árboles"
    PODS = "pods", "Mazorcas"


class SamplingMethod(models.TextChoices):
    ZIGZAG = "zigzag", "Zig-zag"
    FIVE_OF_GOLD = "five_of_gold", "Cinco de oros"
    DIAGONAL = "diagonal", "Diagonal"
    ALL_UNITS = "all_units", "Todas las unidades"


class ControlMethod(models.TextChoices):
    """Qué se hizo contra la plaga. Todos los controles son del mismo tipo de actividad, para que
    el calendario y el historial los muestren juntos; el método dice cómo se atacó."""

    FRUIT_REMOVAL = "fruit_removal", "Remoción de frutos enfermos"
    # Cortar lo enfermo para atacar una detección. La poda de mantenimiento es otra actividad.
    SANITARY_PRUNING = "sanitary_pruning", "Poda sanitaria"
    PRODUCT_APPLICATION = "product_application", "Aplicación de producto"
    OTHER = "other", "Otro"
