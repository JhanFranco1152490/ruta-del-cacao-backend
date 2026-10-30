"""Qué avisos ve cada persona.

Solo los suyos, sin los que eliminó, y de ellos solo los de lo que alcanza hoy: las actividades
con el permiso de verlas y los lotes con el de ver lotes, cada uno en las fincas de la persona. Si
a un empleado le quitan una finca, los avisos de esa finca dejan de verse (y vuelven si se la
devuelven). Así la bandeja nunca muestra una parcela o un lote que la persona ya no puede abrir.
"""

from django.db.models import (
    Case,
    Count,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)

from apps.common.contracts.lot_representation import lot_brief_prefetch
from apps.common.ownership import owner_filter

from ..choices import LOT_KINDS, NotificationSeverity
from ..models import Notification

# La actividad y el volteo se toman de la relación y no de su app: ninguna app importa de otra.
AgriculturalActivity = Notification._meta.get_field("activity").related_model
FermentationTurn = Notification._meta.get_field("fermentation_turn").related_model

VIEW_PERMISSION = "activities.view_agriculturalactivity"
LOT_VIEW_PERMISSION = "lots.view_lot"


def reachable(actor) -> QuerySet[Notification]:
    """Los avisos de la cuenta que alcanza hoy, también los que eliminó (para deshacerlo)."""
    scopes = []
    if actor.has_perm(VIEW_PERMISSION):
        # Los de actividades y los de sanidad, que cuelgan de la actividad del monitoreo.
        scopes.append(
            ~Q(kind__in=LOT_KINDS)
            & Q(
                **owner_filter(
                    actor, "activity__plot__farm__producer_id", farm="activity__plot__farm_id"
                )
            )
        )
    if actor.has_perm(LOT_VIEW_PERMISSION):
        scopes.append(
            Q(kind__in=LOT_KINDS)
            & Q(
                **owner_filter(
                    actor,
                    "lot__harvest__plot__farm__producer_id",
                    farm="lot__harvest__plot__farm_id",
                )
            )
        )
    if not scopes:
        return Notification.objects.none()
    allowed = scopes[0]
    for scope in scopes[1:]:
        allowed |= scope
    return Notification.objects.filter(allowed, recipient=actor)


def visible(actor) -> QuerySet[Notification]:
    """Los que se ven en la bandeja: los que alcanza y no eliminó."""
    return reachable(actor).filter(dismissed_at__isnull=True)


def inbox(actor, *, unread_only=False) -> QuerySet[Notification]:
    """Las críticas sin leer primero; después, de la más reciente a la más antigua. El id
    desempata: con un orden total, una página no repite ni salta avisos de la misma hora."""
    notifications = visible(actor)
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
            # Lo que la representación de cada aviso necesita: sin una consulta por aviso.
            Prefetch(
                "activity",
                queryset=AgriculturalActivity.with_representation(
                    AgriculturalActivity.objects.all()
                ),
            ),
            *lot_brief_prefetch("lot"),
            Prefetch("fermentation_turn", queryset=_numbered_turns()),
            "drying_log",
        )
        .order_by("critical_first", "-created_at", "-id")
    )


def _numbered_turns() -> QuerySet:
    """Los volteos con su número: su posición por hora entre los de su fermentación, como los
    numera la fermentación."""
    up_to_this_one = (
        FermentationTurn.objects.filter(
            process_id=OuterRef("process_id"), turned_at__lte=OuterRef("turned_at")
        )
        .order_by()
        .values("process_id")
        .annotate(count=Count("pk"))
        .values("count")
    )
    return FermentationTurn.objects.annotate(
        number=Subquery(up_to_this_one, output_field=IntegerField())
    )


def unread_count(actor) -> int:
    return visible(actor).filter(read_at__isnull=True).count()
