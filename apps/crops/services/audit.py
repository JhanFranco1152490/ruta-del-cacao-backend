from collections.abc import Iterable

from ..models import CacaoVariety, CacaoVarietyAuditEvent


def record_variety_audit_event(
    *, variety: CacaoVariety, actor, action: str, changed_fields: Iterable[str] = ()
) -> CacaoVarietyAuditEvent:
    return CacaoVarietyAuditEvent.record(
        variety=variety,
        variety_ref=variety.pk,
        variety_name=variety.name,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
    )
