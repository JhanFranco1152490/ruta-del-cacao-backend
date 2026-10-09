from django.db import models

# Van en el código y no en tablas administrables: sanidad, alertas y reportes dependen de ellos,
# y el monitoreo y el control fitosanitario tienen reglas propias. Lo poco frecuente cabe en
# "Otro", con su descripción.


class ActivityType(models.TextChoices):
    PRUNING = "pruning", "Poda"
    FERTILIZATION = "fertilization", "Fertilización"
    IRRIGATION = "irrigation", "Riego"
    WEED_CONTROL = "weed_control", "Control de malezas"
    PHYTOSANITARY_MONITORING = "phytosanitary_monitoring", "Monitoreo fitosanitario"
    # Solo se crea a partir de un hallazgo de un monitoreo, nunca al programar una labor.
    PHYTOSANITARY_CONTROL = "phytosanitary_control", "Control fitosanitario"
    CLEANING_OR_LIMING = "cleaning_or_liming", "Limpieza o encalado"
    # El recordatorio de contar los insumos o herramientas de la bodega.
    INVENTORY = "inventory", "Inventario"
    OTHER = "other", "Otro"


class ActivityStatus(models.TextChoices):
    """Lo que se guarda. Retrasada y vencida no se guardan: salen de la fecha programada, y una
    tarea periódica que las cambiara dejaría el estado guardado desactualizado mientras no
    corre."""

    SCHEDULED = "scheduled", "Programada"
    DONE = "done", "Realizada"
