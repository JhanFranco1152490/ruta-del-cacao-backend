"""Las actividades en la bitácora de cambios."""

from apps.common.contracts.audit_log import (
    KIND_DATE,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
    names_by_id,
    referenced_ids,
)
from apps.common.serializers import full_name

from .choices import ActivityStatus, ActivityType
from .models import AgriculturalActivity, AgriculturalActivityAuditEvent, AgriculturalActivityInput

# Los modelos de las otras apps se toman de las relaciones: ninguna app importa de otra.
Plot = AgriculturalActivity._meta.get_field("plot").related_model
Account = AgriculturalActivity._meta.get_field("assignee").related_model
Input = AgriculturalActivityInput._meta.get_field("input").related_model

LABELS = {
    "activity_type": "Tipo",
    "other_description": "Descripción",
    "scheduled_date": "Fecha programada",
    "assignee_id": "Responsable",
    "status": "Estado",
    "done_date": "Fecha de realización",
    "inputs": "Insumos usados",
}
KINDS = {"scheduled_date": KIND_DATE, "done_date": KIND_DATE}
TYPES = dict(ActivityType.choices)


def events(producer_id, **filters):
    return audit_events(AgriculturalActivityAuditEvent.objects.all(), producer_id, **filters)


def _used_inputs(changes: dict, names: dict) -> dict:
    """Los insumos usados (`[{input_id, quantity}]`) como texto: «Urea: 2.000»."""
    used = changes.get("inputs")
    if not used:
        return changes

    def text(rows):
        if not rows:
            return None
        return "; ".join(
            f"{names.get(str(row['input_id']), row['input_id'])}: {row['quantity']}"
            for row in rows
        )

    return {**changes, "inputs": {side: text(used.get(side)) for side in ("before", "after")}}


def _input_ids(found) -> set[str]:
    ids = set()
    for event in found:
        for side in ("before", "after"):
            for row in ((event.changes or {}).get("inputs") or {}).get(side) or []:
                ids.add(str(row["input_id"]))
    return ids


def _label(event, plots: dict) -> str:
    """«Poda · P01»: el tipo de la actividad (de ella, o de lo que guardó el evento si ya se
    eliminó) y su parcela."""
    activity = event.activity
    if activity is not None:
        kind = activity.activity_type
    else:
        values = (event.changes or {}).get("activity_type") or {}
        kind = values.get("before") or values.get("after")
    task = TYPES.get(kind, "Actividad")
    plot = plots.get(str(event.plot_ref))
    return f"{task} · {plot}" if plot else task


def describe(ids):
    found = list(
        AgriculturalActivityAuditEvent.objects.filter(pk__in=ids).select_related(
            "actor", "activity"
        )
    )
    plots = names_by_id(Plot, {event.plot_ref for event in found}, lambda plot: plot.code)
    accounts = names_by_id(Account, referenced_ids(found, "assignee_id"), full_name)
    inputs = names_by_id(Input, _input_ids(found), lambda item: item.name)
    names = {
        "activity_type": TYPES,
        "status": dict(ActivityStatus.choices),
        "assignee_id": accounts,
    }
    return [
        audit_entry(
            event,
            "activity",
            record_id=event.activity_ref,
            record_label=_label(event, plots),
            record_deleted=event.activity_id is None,
            changes=audit_changes(
                _used_inputs(event.changes or {}, inputs),
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                names=names,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
