"""Las fincas en la bitácora de cambios."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
)
from apps.common.territorial import InvalidMunicipalityCode, get_municipality

from .models import FarmAuditEvent

LABELS = {
    "name": "Nombre",
    "municipality_code": "Municipio",
    "area_hectares": "Área (ha)",
    "altitude_masl": "Altitud (m s. n. m.)",
    "latitude": "Latitud",
    "longitude": "Longitud",
    "details": "Detalles",
    "is_active": "Activa",
}
KINDS = {
    "area_hectares": KIND_NUMBER,
    "altitude_masl": KIND_NUMBER,
    "latitude": KIND_NUMBER,
    "longitude": KIND_NUMBER,
    "is_active": KIND_BOOL,
}


def events(producer_id, **filters):
    return audit_events(FarmAuditEvent.objects.all(), producer_id, **filters)


def _municipalities(events) -> dict[str, str]:
    names = {}
    for event in events:
        values = (event.changes or {}).get("municipality_code") or {}
        for code in (values.get("before"), values.get("after")):
            if code and code not in names:
                try:
                    names[code] = get_municipality(code).name
                except InvalidMunicipalityCode:
                    continue
    return names


def _label(event) -> str:
    # El nombre de la copia: sirve también si la finca ya se eliminó.
    if event.farm is None:
        return event.farm_name
    return f"{event.farm.code} · {event.farm_name}"


def describe(ids):
    found = list(FarmAuditEvent.objects.filter(pk__in=ids).select_related("actor", "farm"))
    municipalities = _municipalities(found)
    return [
        audit_entry(
            event,
            "farm",
            record_id=event.farm_ref,
            record_label=_label(event),
            record_deleted=event.farm_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                names={"municipality_code": municipalities},
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
