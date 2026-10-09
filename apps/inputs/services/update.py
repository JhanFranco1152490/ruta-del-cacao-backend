import copy
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.audit import record_update_events
from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import InputNotFound, InputUnitLocked, StaleInputVersion
from ..models import AgriculturalInput, AgriculturalInputAuditEvent
from ..usage import is_used
from .audit import record_input_audit_event
from .create import CONTENT_FIELDS, NAME_UNIQUE_CONSTRAINT, duplicate_error

# Cambiarla cambiaría lo que significan las cantidades ya registradas. La presentación no: solo
# cambia cómo se muestran y se capturan.
LOCKED_WHEN_USED = ("unit",)


@transaction.atomic
def update_input(actor, input_id, expected_version: int, data: dict) -> AgriculturalInput:
    """Edita un insumo, incluida su activación o desactivación. Sin cambios reales devuelve el
    insumo tal cual, sin subir la versión ni dejar historial."""
    try:
        item = AgriculturalInput.objects.select_for_update().get(
            pk=input_id, **owner_filter(actor)
        )
    except AgriculturalInput.DoesNotExist:
        raise InputNotFound() from None

    if check_expected_version(
        item,
        expected_version,
        stale=lambda: StaleInputVersion(_with_usage(item)),
        already_applied=lambda: _already_applied(item, data),
    ):
        return _with_usage(item)

    before = {name: getattr(item, name) for name in CONTENT_FIELDS}
    _apply(item, data)
    item.full_clean(validate_unique=False, validate_constraints=False)
    # Se compara después de validar: un nombre que solo cambió en espacios no es un cambio.
    changed = [name for name in CONTENT_FIELDS if getattr(item, name) != before[name]]
    if not changed:
        return _with_usage(item)

    used = is_used(item)
    for name in LOCKED_WHEN_USED:
        if used and name in changed:
            raise InputUnitLocked(name)

    update_fields = [*changed, "name_normalized"] if "name" in changed else changed
    save_next_version(
        item,
        update_fields,
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=lambda: duplicate_error(item),
    )
    record_update_events(
        partial(record_input_audit_event, item=item, actor=actor, before=before),
        changed,
        updated=AgriculturalInputAuditEvent.Action.UPDATED,
        status_changed=AgriculturalInputAuditEvent.Action.STATUS_CHANGED,
    )
    item.has_records = used
    return item


def _apply(item: AgriculturalInput, data: dict) -> None:
    for name, value in data.items():
        setattr(item, name, value)


def _already_applied(item: AgriculturalInput, data: dict) -> bool:
    """Si el insumo ya tiene lo que se pide: una cola o un doble clic reintenta aunque el servidor
    haya aplicado el cambio. Se compara después de limpiar como al guardar."""
    candidate = copy.copy(item)
    _apply(candidate, data)
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError:
        return False
    return all(getattr(candidate, name) == getattr(item, name) for name in CONTENT_FIELDS)


def _with_usage(item: AgriculturalInput) -> AgriculturalInput:
    item.has_records = is_used(item)
    return item
