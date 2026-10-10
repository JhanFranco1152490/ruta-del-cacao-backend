from django.db import transaction
from django.db.models import ProtectedError

from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version

from ..exceptions import InputHasRecords, InputNotFound, StaleInputVersion
from ..models import AgriculturalInput, AgriculturalInputAuditEvent
from ..usage import is_used
from .audit import record_input_audit_event


@transaction.atomic
def delete_input(actor, input_id, expected_version: int) -> None:
    """Elimina un insumo registrado por error. Solo si ningún registro lo usa; el que se usa se
    desactiva. Su historial se conserva y el borrado queda registrado en él."""
    try:
        item = AgriculturalInput.objects.select_for_update().get(
            pk=input_id, **owner_filter(actor)
        )
    except AgriculturalInput.DoesNotExist:
        raise InputNotFound() from None
    check_expected_version(item, expected_version, stale=lambda: _stale(item))
    remove_input(item, actor)


def remove_input(item: AgriculturalInput, actor) -> None:
    """Elimina `item` y deja el rastro. Quien llama ya validó quién puede hacerlo: aquí solo se
    aplica la regla. Si algo lo usa, `InputHasRecords` y no se toca nada."""
    if is_used(item):
        raise InputHasRecords()
    record_input_audit_event(
        item=item, actor=actor, action=AgriculturalInputAuditEvent.Action.DELETED
    )
    try:
        item.delete()
    except ProtectedError:
        # Un registro que apunta al insumo apareció entre la revisión y el borrado: la base es
        # la garantía final. La transacción de quien llama deshace también el evento.
        raise InputHasRecords() from None


def _stale(item: AgriculturalInput) -> StaleInputVersion:
    item.has_records = is_used(item)
    return StaleInputVersion(item)
