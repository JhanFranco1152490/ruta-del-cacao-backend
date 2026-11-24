"""Lo que cada app ofrece a la bitácora de cambios.

Cada app guarda el historial de sus registros (`AuditEventBase`, y las cuentas el suyo). La
bitácora los junta en una sola lista, de lo más reciente a lo más antiguo. Ninguna app importa de
otra (ver AGENTS.md): cada dueña registra en su `ready()`, por cada tipo de registro suyo, una
fuente con dos funciones:

- `events(producer_id, *, date_from, date_to, actor_id)`: un queryset de sus eventos con solo `id`,
  `occurred_at` y `actor_id`, para que la bitácora los una y pagine en la base;
- `describe(ids)`: los eventos de una página como `AuditEntry`, ya traducidos (nombres en vez de
  ids, etiquetas, datos personales ocultos), nunca modelos.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.utils import timezone

from ..serializers import full_name
from .sources import SourceRegistry

# Los tipos de registro de la bitácora, en el orden en que se ofrecen para filtrar.
AUDIT_RECORD_TYPES = (
    "farm",
    "plot",
    "plot_characterization",
    "input",
    "activity",
    "harvest",
    "lot",
    "facility",
    "fermentation",
    "drying",
    "quality",
    "stock",
    "warehouse",
    "buyer",
    "sale",
    "account",
    "role",
)

RECORD_TYPE_LABELS = {
    "farm": "Finca",
    "plot": "Parcela",
    "plot_characterization": "Ficha de la parcela",
    "input": "Insumo",
    "activity": "Actividad",
    "harvest": "Cosecha",
    "lot": "Lote",
    "facility": "Cajón o marquesina",
    "fermentation": "Fermentación",
    "drying": "Secado",
    "quality": "Calidad",
    "stock": "Existencias",
    "warehouse": "Bodega",
    "buyer": "Comprador",
    "sale": "Venta",
    "account": "Cuenta",
    "role": "Rol",
}

# Por qué un cambio sale sin sus valores.
HIDDEN_PERSONAL = "personal"
HIDDEN_NOT_RECORDED = "not_recorded"
# Lo que no se muestra como valor aunque se sepa que cambió (el polígono de una parcela).
HIDDEN_NOT_SHOWN = "not_shown"

# Cómo se muestra un valor.
KIND_TEXT = "text"
KIND_NUMBER = "number"
KIND_DATE = "date"
KIND_DATETIME = "datetime"
KIND_BOOL = "bool"


@dataclass(frozen=True)
class AuditChange:
    field: str
    label: str
    kind: str
    # Nulos si el campo es un dato personal o se guardó sin valores (`hidden` dice cuál).
    before: Any
    after: Any
    hidden: str | None = None


@dataclass(frozen=True)
class AuditEntry:
    id: Any
    occurred_at: datetime
    # Sin nombre si la cuenta se eliminó.
    actor_id: Any | None
    actor_name: str | None
    record_type: str
    record_id: Any
    # Lo que nombra al registro, también si ya se eliminó.
    record_label: str
    record_deleted: bool
    action: str
    action_label: str
    changes: tuple[AuditChange, ...]


@dataclass(frozen=True)
class AuditActor:
    id: Any
    full_name: str
    is_active: bool


@dataclass(frozen=True)
class AuditSource:
    events: Callable[..., Any]
    describe: Callable[[list], list[AuditEntry]]


_sources = SourceRegistry("de la bitácora", AUDIT_RECORD_TYPES)
_actors: Callable[[Any], list[AuditActor]] | None = None


def register_audit_source(record_type: str, source: AuditSource) -> None:
    _sources.register(record_type, source)


def audit_source(record_type: str) -> AuditSource:
    return _sources.get(record_type)


def register_audit_actors(source: Callable[[Any], list[AuditActor]]) -> None:
    """Las cuentas de un productor, que se ofrecen para filtrar por usuario. Las registra la app de
    cuentas."""
    global _actors
    _actors = source


def audit_actors(producer_id) -> list[AuditActor]:
    if _actors is None:
        raise RuntimeError("Ninguna app registró las cuentas de la bitácora.")
    return _actors(producer_id)


def local_day_bounds(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """El periodo como `[inicio, fin)` en hora de Bogotá: del comienzo del primer día al del día
    siguiente al último. Un lado sin fecha queda abierto."""

    def midnight(day: date) -> datetime:
        return timezone.make_aware(datetime.combine(day, time.min))

    start = midnight(date_from) if date_from is not None else None
    end = midnight(date_to + timedelta(days=1)) if date_to is not None else None
    return start, end


def audit_events(
    queryset,
    producer_id,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    actor_id=None,
    producer_field: str = "producer_ref",
):
    """Los eventos de `queryset` de ese productor que cumplen el periodo y el autor, con solo
    `id`, `occurred_at` y `actor_id`: lo que la bitácora une. No consulta la base."""
    events = queryset.filter(**{producer_field: producer_id})
    start, end = local_day_bounds(date_from, date_to)
    if start is not None:
        events = events.filter(occurred_at__gte=start)
    if end is not None:
        events = events.filter(occurred_at__lt=end)
    if actor_id is not None:
        events = events.filter(actor_id=actor_id)
    return events.values("id", "occurred_at", "actor_id")


def audit_changes(
    stored: Mapping[str, Mapping[str, Any]],
    *,
    labels: Mapping[str, str],
    changed_fields: Iterable[str] = (),
    kinds: Mapping[str, str] | None = None,
    personal: Iterable[str] = (),
    names: Mapping[str, Mapping[Any, str]] | None = None,
    not_shown: Iterable[str] = (),
    skip: Iterable[str] = (),
) -> tuple[AuditChange, ...]:
    """Los cambios guardados de un evento (`{campo: {before, after}}`, el formato de
    `field_changes`) como los muestra la bitácora.

    Cada campo lleva su etiqueta de `labels` (o su nombre) y su `kind` (texto por defecto). Un id
    con nombre en `names` sale por su nombre; uno que ya no tiene nombre, tal cual. Un campo de
    `personal` sale sin valores; uno de `not_shown`, también (se sabe que cambió, pero no se
    muestra); uno que solo está en `changed_fields` (un evento guardado sin valores), como no
    registrado. Los de `skip` no salen. Van en el orden de `labels` y después por nombre.
    """
    kinds = kinds or {}
    names = names or {}
    personal = set(personal)
    not_shown = set(not_shown)
    fields = (set(stored) | set(changed_fields)) - set(skip)
    order = {field: position for position, field in enumerate(labels)}
    ordered = sorted(fields, key=lambda field: (order.get(field, len(order)), field))
    changes = []
    for field in ordered:
        label = labels.get(field, field)
        if field in personal or field in not_shown or field not in stored:
            if field in personal:
                hidden = HIDDEN_PERSONAL
            elif field in not_shown:
                hidden = HIDDEN_NOT_SHOWN
            else:
                hidden = HIDDEN_NOT_RECORDED
            changes.append(
                AuditChange(field, label, kinds.get(field, KIND_TEXT), None, None, hidden)
            )
            continue
        values = stored[field]
        translate = names.get(field)
        if translate is not None:
            before, after = (_named(translate, values.get(side)) for side in ("before", "after"))
            changes.append(AuditChange(field, label, KIND_TEXT, before, after))
        else:
            kind = kinds.get(field, KIND_TEXT)
            changes.append(
                AuditChange(field, label, kind, values.get("before"), values.get("after"))
            )
    return tuple(changes)


def _named(translate: Mapping[Any, str], value):
    if value is None:
        return None
    return translate.get(value, value)


def audit_entry(
    event,
    record_type: str,
    *,
    record_id,
    record_label: str,
    record_deleted: bool,
    changes: tuple[AuditChange, ...],
) -> AuditEntry:
    """La entrada de un evento de un historial (con `actor` ya cargado): su hora, quién lo hizo
    (sin nombre si la cuenta se eliminó) y su acción con la etiqueta de sus opciones. Cada fuente
    aporta el registro y sus cambios."""
    actor = event.actor
    return AuditEntry(
        id=event.pk,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        actor_name=None if actor is None else full_name(actor),
        record_type=record_type,
        record_id=record_id,
        record_label=record_label,
        record_deleted=record_deleted,
        action=event.action,
        action_label=event.get_action_display(),
        changes=changes,
    )


def referenced_ids(events, *fields: str) -> set[str]:
    """Los valores (ids) de esos campos en los cambios guardados de `events`, antes y después,
    para traducirlos a nombres con una sola consulta."""
    found = set()
    for event in events:
        for field in fields:
            values = (event.changes or {}).get(field) or {}
            found.update(
                str(value)
                for value in (values.get("before"), values.get("after"))
                if value is not None
            )
    return found


def names_by_id(model, ids: Iterable, label: Callable[[Any], str] = str) -> dict[str, str]:
    """El nombre de cada registro de `model` con esos ids, con la clave como texto (como guarda
    el historial los ids). Una consulta; un id que ya no existe no sale."""
    ids = [value for value in ids if value]
    if not ids:
        return {}
    return {str(pk): label(record) for pk, record in model.objects.in_bulk(ids).items()}
