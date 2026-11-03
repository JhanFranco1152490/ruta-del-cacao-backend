from apps.common.audit import field_changes

from ..models import ONE_DECIMAL, QualityAuditEvent

# Lo que describe una evaluación, con los valores que entrega la API.
EVALUATION_FIELDS = ("well_fermented_pct", "moldy_pct", "other_defects_pct", "notes")


def evaluation_values(evaluation) -> dict:
    return {field: getattr(evaluation, field) for field in EVALUATION_FIELDS}


def record_quality_event(*, lot, actor, action: str, before: dict, after: dict, version: int):
    changes = field_changes(before, after, decimal_places=ONE_DECIMAL)
    return QualityAuditEvent.record(
        lot=lot,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=version,
        changes=changes,
    )
