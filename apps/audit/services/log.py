"""La bitácora de cambios de un productor: los historiales de todas las apps en una sola lista, de
lo más reciente a lo más antiguo.

Cada app ofrece su historial por el contrato de la bitácora. Aquí se unen en la base con solo
`id`, `occurred_at`, `actor_id` y el tipo de registro, se ordenan y se paginan, y solo los eventos
de la página se piden a su app para traducirlos.
"""

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import CharField, Value
from rest_framework.exceptions import ValidationError

from apps.common.contracts.audit_log import (
    AUDIT_RECORD_TYPES,
    RECORD_TYPE_LABELS,
    AuditActor,
    AuditEntry,
    audit_actors,
    audit_source,
)

from ..exceptions import AuditFilterNotFound


@dataclass(frozen=True)
class AuditOptions:
    actors: list[AuditActor]
    record_types: list[dict]


def _producer_of(actor, filters: dict):
    """El productor cuya bitácora se lee: el propio; la cuenta técnica lo elige, y debe existir
    (todo productor tiene al menos su cuenta)."""
    if not actor.is_superuser:
        return actor.producer_id, audit_actors(actor.producer_id)
    producer_id = filters.get("producer")
    if producer_id is None:
        raise ValidationError({"producer": ["Elige el productor cuya bitácora quieres ver."]})
    actors = audit_actors(producer_id)
    if not actors:
        raise AuditFilterNotFound("producer")
    return producer_id, actors


def audit_log_rows(actor, filters: dict):
    """La unión de los eventos que cumplen los filtros, ordenada y sin evaluar: la paginación la
    corta en la base. Cada fila trae `id`, `occurred_at`, `actor_id` y `record_type`."""
    producer_id, actors = _producer_of(actor, filters)
    actor_id = filters.get("actor")
    if actor_id is not None and actor_id not in {account.id for account in actors}:
        raise AuditFilterNotFound("actor")
    types = [filters["record_type"]] if "record_type" in filters else list(AUDIT_RECORD_TYPES)
    queries = [
        audit_source(record_type)
        .events(
            producer_id,
            date_from=filters.get("from"),
            date_to=filters.get("to"),
            actor_id=actor_id,
        )
        .annotate(record_type=Value(record_type, output_field=CharField()))
        for record_type in types
    ]
    first, *others = queries
    rows = first.union(*others, all=True) if others else first
    return rows.order_by("-occurred_at", "-id")


def describe_rows(rows) -> list[AuditEntry]:
    """Los eventos de una página, traducidos por su app y en el orden de la página."""
    by_type = defaultdict(list)
    for row in rows:
        by_type[row["record_type"]].append(row["id"])
    entries = {}
    for record_type, ids in by_type.items():
        for entry in audit_source(record_type).describe(ids):
            entries[entry.id] = entry
    return [entries[row["id"]] for row in rows if row["id"] in entries]


def audit_options(actor, filters: dict) -> AuditOptions:
    _producer_id, actors = _producer_of(actor, filters)
    return AuditOptions(
        actors=actors,
        record_types=[
            {"value": record_type, "label": RECORD_TYPE_LABELS[record_type]}
            for record_type in AUDIT_RECORD_TYPES
        ],
    )
