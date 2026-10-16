from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from apps.common.alerts import evaluators
from apps.common.exceptions import log_unhandled_error

from ..models import Notification
from .create import create_notifications

# Cuánto se guarda un aviso que ya se leyó o se eliminó y cuya condición ya pasó.
KEEP_DAYS = 90
# El estado guardado de una actividad realizada. Va como texto porque esta app no importa de
# la de actividades.
DONE_STATUS = "done"


@dataclass
class EvaluationResult:
    created: dict[str, int] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    purged: int = 0


def evaluation_date(now):
    """El día que se evalúa: el de Bogotá, la zona del proyecto. La medianoche que cuenta es la
    de allá, no la UTC."""
    return timezone.localdate(now)


def evaluate_alerts(today, now) -> EvaluationResult:
    """Corre cada evaluador registrado y guarda los avisos nuevos. Un evaluador que falla no
    detiene a los demás: su error queda registrado y la siguiente evaluación lo vuelve a
    intentar, sin repetir lo que ya se avisó."""
    result = EvaluationResult()
    for name, evaluate in evaluators().items():
        try:
            result.created[name] = create_notifications(list(evaluate(today)))
        except Exception as exc:
            log_unhandled_error(exc, where=f"el evaluador {name}")
            result.failed.append(name)
    result.purged = _purge(now)
    return result


def _purge(now) -> int:
    """Borra los avisos leídos o eliminados de hace más de `KEEP_DAYS` cuya condición ya pasó
    (la actividad se realizó o se reprogramó). Uno de una actividad que sigue vencida se queda:
    sin él, la siguiente evaluación avisaría otra vez."""
    passed = Q(activity__status=DONE_STATUS) | ~Q(activity__scheduled_date=F("condition_date"))
    deleted, _ = (
        Notification.objects.filter(
            Q(read_at__isnull=False) | Q(dismissed_at__isnull=False),
            passed,
            created_at__lt=now - timedelta(days=KEEP_DAYS),
        )
        .only("pk")
        .delete()
    )
    return deleted
