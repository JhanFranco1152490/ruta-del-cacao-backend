from django.db import transaction
from django.db.models import ProtectedError

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version

from ..exceptions import (
    FacilityHasRecords,
    FacilityNotFound,
    FacilityOccupied,
    StaleFacilityVersion,
)
from ..models import PostharvestFacility, PostharvestFacilityAuditEvent
from ..usage import is_used
from .audit import record_facility_audit_event


@transaction.atomic
def delete_facility(actor, facility_id, expected_version: int) -> None:
    """Elimina un cajón o una marquesina registrado por error. Solo si nunca se usó; el que se usó
    se desactiva. Su historial se conserva y el borrado queda registrado en él."""
    facility, _farm = lock_aggregate_root(
        PostharvestFacility,
        facility_id,
        root="farm",
        scope=owner_filter(actor, "farm__producer_id", farm="farm_id"),
        not_found=FacilityNotFound,
    )
    check_expected_version(facility, expected_version, stale=lambda: _stale(facility))
    remove_facility(facility, actor)


def remove_facility(facility: PostharvestFacility, actor) -> None:
    """Elimina `facility` y deja el rastro. Quien llama ya validó quién puede hacerlo: aquí solo se
    aplica la regla. Si algo lo usa, `FacilityHasRecords` y no se toca nada."""
    if facility.current_lot_id is not None:
        raise FacilityOccupied(facility.current_lot)
    if is_used(facility):
        raise FacilityHasRecords()
    record_facility_audit_event(
        facility=facility, actor=actor, action=PostharvestFacilityAuditEvent.Action.DELETED
    )
    try:
        # Solo si sigue libre: ocupar no toma un bloqueo propio (confía en que quien lo llama
        # bloqueó la finca), así que se vuelve a mirar en el mismo borrado.
        deleted, _ = PostharvestFacility.objects.filter(
            pk=facility.pk, current_lot__isnull=True
        ).delete()
    except ProtectedError:
        # Un registro que apunta al elemento apareció entre la revisión y el borrado: la base es
        # la garantía final. La transacción de quien llama deshace también el evento.
        raise FacilityHasRecords() from None
    if not deleted:
        raise FacilityOccupied(
            PostharvestFacility.objects.select_related("current_lot")
            .get(pk=facility.pk)
            .current_lot
        )


def _stale(facility: PostharvestFacility) -> StaleFacilityVersion:
    facility.has_records = is_used(facility)
    return StaleFacilityVersion(facility)
