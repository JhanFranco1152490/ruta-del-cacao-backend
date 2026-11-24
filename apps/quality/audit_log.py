"""La calidad de los lotes en la bitácora de cambios: la evaluación, la clasificación y el
descarte."""

from apps.common.contracts.audit_log import (
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
)

from .choices import DiscardReason
from .models import QualityAuditEvent

REASONS = dict(DiscardReason.choices)
LABELS = {
    "well_fermented_pct": "Bien fermentados (%)",
    "moldy_pct": "Con moho (%)",
    "other_defects_pct": "Otros defectos (%)",
    "notes": "Notas",
    "g1_kg": "G1 (kg)",
    "g2_kg": "G2 (kg)",
    "discard_kg": "Descarte (kg)",
    "discard_reason": "Motivo del descarte",
    "discard_detail": "Detalle del descarte",
    "reason": "Motivo del descarte",
    "detail": "Detalle del descarte",
}
NUMBERS = ("well_fermented_pct", "moldy_pct", "other_defects_pct", "g1_kg", "g2_kg", "discard_kg")
KINDS = {field: KIND_NUMBER for field in NUMBERS}
NAMES = {"discard_reason": REASONS, "reason": REASONS}


def events(producer_id, **filters):
    return audit_events(QualityAuditEvent.objects.all(), producer_id, **filters)


def describe(ids):
    found = QualityAuditEvent.objects.filter(pk__in=ids).select_related("actor", "lot")
    return [
        audit_entry(
            event,
            "quality",
            record_id=event.lot_id,
            record_label=event.lot.code,
            # Un lote con calidad no se elimina.
            record_deleted=False,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                names=NAMES,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
