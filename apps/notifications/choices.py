from django.db import models


class NotificationKind(models.TextChoices):
    ACTIVITY_UPCOMING = "activity_upcoming", "Actividad próxima"
    ACTIVITY_DELAYED = "activity_delayed", "Actividad retrasada"
    ACTIVITY_OVERDUE = "activity_overdue", "Actividad vencida"
    DETECTION_CONTROL_PENDING = "detection_control_pending", "Control pendiente"


# Los tipos que hablan de una actividad: todos llevan la actividad.
ACTIVITY_KINDS = (
    NotificationKind.ACTIVITY_UPCOMING,
    NotificationKind.ACTIVITY_DELAYED,
    NotificationKind.ACTIVITY_OVERDUE,
)


class NotificationSeverity(models.TextChoices):
    NORMAL = "normal", "Normal"
    # Va primero en la bandeja mientras no se lea.
    CRITICAL = "critical", "Crítica"
