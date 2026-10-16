"""Qué avisos ve cada persona.

Solo los suyos, sin los que eliminó, y de ellos solo los de actividades que alcanza hoy: si a un
empleado le quitan una finca, los avisos de esa finca dejan de verse (y vuelven si se la
devuelven). Así la bandeja nunca muestra una parcela que la persona ya no puede abrir.
"""

from django.db.models import Case, IntegerField, Prefetch, QuerySet, Value, When

from apps.common.ownership import owner_filter

from ..choices import NotificationSeverity
from ..models import Notification

# La actividad se toma de la relación y no de su app: ninguna app importa de otra.
AgriculturalActivity = Notification._meta.get_field("activity").related_model

VIEW_PERMISSION = "activities.view_agriculturalactivity"


def _visible(actor) -> QuerySet[Notification]:
    if not actor.has_perm(VIEW_PERMISSION):
        return Notification.objects.none()
    return Notification.objects.filter(
        recipient=actor,
        dismissed_at__isnull=True,
        **owner_filter(actor, "activity__plot__farm__producer_id", farm="activity__plot__farm_id"),
    )


def inbox(actor, *, unread_only=False) -> QuerySet[Notification]:
    """Las críticas sin leer primero; después, de la más reciente a la más antigua. El id
    desempata: con un orden total, una página no repite ni salta avisos de la misma hora."""
    notifications = _visible(actor)
    if unread_only:
        notifications = notifications.filter(read_at__isnull=True)
    return (
        notifications.annotate(
            critical_first=Case(
                When(severity=NotificationSeverity.CRITICAL, read_at__isnull=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .prefetch_related(
            # La actividad con lo que su representación necesita: sin una consulta por aviso.
            Prefetch(
                "activity",
                queryset=AgriculturalActivity.with_representation(
                    AgriculturalActivity.objects.all()
                ),
            )
        )
        .order_by("critical_first", "-created_at", "-id")
    )


def unread_count(actor) -> int:
    return _visible(actor).filter(read_at__isnull=True).count()
