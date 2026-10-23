"""Los avisos de desvío del secado: secado lento, acelerado, próximo a la meta y sobresecado.

El servicio de la bitácora llama a `drying_log_alerts` al registrar y al corregir, con la bitácora
ya guardada, y manda lo que devuelve a notificar. Las reglas de cada desvío se escriben aquí, con
los umbrales del productor (`drying_parameters`); mientras no haya ninguna, no se genera aviso.
"""

from apps.common.contracts.alerts import NotificationDraft


def drying_log_alerts(entry) -> list[NotificationDraft]:
    return []
