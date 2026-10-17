"""Lo que los servicios de sanidad comparten sobre la actividad a la que están unidos."""

from apps.common.ownership import owner_filter

from ..models import PhytosanitaryMonitoring

# El modelo de la actividad se toma de la relación y no de su app: ninguna app importa de otra.
AgriculturalActivity = PhytosanitaryMonitoring._meta.get_field("activity").related_model

# El estado de una actividad realizada y los permisos que decide la app de actividades.
ACTIVITY_DONE = "done"
SCHEDULE_PERMISSION = "activities.add_agriculturalactivity"
COMPLETE_PERMISSION = "activities.complete_agriculturalactivity"

# De una detección a su finca, que es la raíz que se bloquea y de donde sale el alcance.
DETECTION_FARM = "monitoring__activity__plot__farm"


def activity_scope(actor) -> dict:
    """Filtro de las actividades que `actor` alcanza."""
    return owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id")


def detection_scope(actor) -> dict:
    """Filtro de las detecciones que `actor` alcanza."""
    return owner_filter(actor, f"{DETECTION_FARM}__producer_id", farm=f"{DETECTION_FARM}_id")
