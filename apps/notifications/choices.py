from django.db import models


class NotificationKind(models.TextChoices):
    ACTIVITY_UPCOMING = "activity_upcoming", "Actividad próxima"
    ACTIVITY_DELAYED = "activity_delayed", "Actividad retrasada"
    ACTIVITY_OVERDUE = "activity_overdue", "Actividad vencida"
    DETECTION_CONTROL_PENDING = "detection_control_pending", "Control pendiente"
    FERMENTATION_FIRST_TURN_DUE = "fermentation_first_turn_due", "Primer volteo próximo"
    FERMENTATION_TURN_DUE = "fermentation_turn_due", "Volteo pendiente"
    DRYING_LOG_DUE = "drying_log_due", "Bitácora de secado pendiente"
    FERMENTATION_TEMPERATURE_LOW = "fermentation_temperature_low", "Temperatura baja"
    FERMENTATION_TEMPERATURE_HIGH = "fermentation_temperature_high", "Temperatura alta"
    FERMENTATION_PH_LOW = "fermentation_ph_low", "Grano demasiado ácido"
    FERMENTATION_PH_HIGH = "fermentation_ph_high", "Fermentación que no avanza"
    DRYING_SLOW_STALLED = "drying_slow_stalled", "Secado lento por estancamiento"
    DRYING_SLOW_DURATION = "drying_slow_duration", "Secado lento por duración"
    DRYING_ACCELERATED = "drying_accelerated", "Secado acelerado"
    DRYING_NEAR_TARGET = "drying_near_target", "Próximo a meta"
    DRYING_OVERDRIED = "drying_overdried", "Sobresecado"


# Los tipos que hablan de una actividad: todos llevan la actividad.
ACTIVITY_KINDS = (
    NotificationKind.ACTIVITY_UPCOMING,
    NotificationKind.ACTIVITY_DELAYED,
    NotificationKind.ACTIVITY_OVERDUE,
)

# Lo que falta registrar de un lote. Quedan resueltos cuando llega el registro o el lote termina la
# etapa.
PENDING_FERMENTATION_KINDS = (
    NotificationKind.FERMENTATION_FIRST_TURN_DUE,
    NotificationKind.FERMENTATION_TURN_DUE,
)
PENDING_LOT_KINDS = (*PENDING_FERMENTATION_KINDS, NotificationKind.DRYING_LOG_DUE)

# Lo que un registro midió fuera de los parámetros: cada uno lleva su registro.
FERMENTATION_DEVIATION_KINDS = (
    NotificationKind.FERMENTATION_TEMPERATURE_LOW,
    NotificationKind.FERMENTATION_TEMPERATURE_HIGH,
    NotificationKind.FERMENTATION_PH_LOW,
    NotificationKind.FERMENTATION_PH_HIGH,
)
DRYING_DEVIATION_KINDS = (
    NotificationKind.DRYING_SLOW_STALLED,
    NotificationKind.DRYING_SLOW_DURATION,
    NotificationKind.DRYING_ACCELERATED,
    NotificationKind.DRYING_NEAR_TARGET,
    NotificationKind.DRYING_OVERDRIED,
)

# Los tipos que hablan de un lote: todos llevan el lote.
LOT_KINDS = (*PENDING_LOT_KINDS, *FERMENTATION_DEVIATION_KINDS, *DRYING_DEVIATION_KINDS)


class NotificationSeverity(models.TextChoices):
    NORMAL = "normal", "Normal"
    # Va primero en la bandeja mientras no se lea.
    CRITICAL = "critical", "Crítica"
