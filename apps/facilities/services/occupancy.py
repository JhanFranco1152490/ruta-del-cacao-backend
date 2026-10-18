"""Ocupar y liberar un cajón o una marquesina.

No toman un bloqueo propio: quien las llama (fermentación, secado) ya tiene bloqueada la finca del
lote, que es la del elemento (un lote solo usa los de su finca), como toda escritura bajo una
finca. El cambio es una sola actualización condicional de la
fila: solo ocupa si en ese instante el elemento es del tipo pedido, está activo y está libre, y
solo libera si adentro está ese lote. Dos que se cruzan no pueden ganar los dos: PostgreSQL vuelve
a evaluar la condición del segundo cuando el primero confirma.
"""

from django.db.models import F
from django.utils import timezone

from ..exceptions import (
    FacilityNotFound,
    FacilityNotOccupiedByLot,
    FacilityOtherFarm,
    FacilityUnavailable,
    FacilityWrongType,
)
from ..models import PostharvestFacility, PostharvestFacilityAuditEvent
from ..status import FacilityStatus
from .audit import record_occupancy_event


def occupy_facility(
    facility: PostharvestFacility, lot, *, kind: str, actor
) -> PostharvestFacility:
    lot_farm = lot.harvest.plot.farm
    if facility.farm.producer_id != lot_farm.producer_id:
        # Un elemento de otro productor no existe para este lote: responder distinto
        # confirmaría que existe.
        raise FacilityNotFound()
    if facility.farm_id != lot_farm.pk:
        raise FacilityOtherFarm()
    now = timezone.now()
    occupied = PostharvestFacility.objects.filter(
        pk=facility.pk, facility_type=kind, is_active=True, current_lot__isnull=True
    ).update(current_lot=lot, occupied_since=now, version=F("version") + 1, updated_at=now)
    if not occupied:
        raise _why_not_occupied(facility.pk, kind)
    facility.refresh_from_db()
    record_occupancy_event(
        facility=facility,
        actor=actor,
        action=PostharvestFacilityAuditEvent.Action.OCCUPIED,
        before_lot=None,
        after_lot=lot,
    )
    return facility


def release_facility(facility: PostharvestFacility, lot, *, actor) -> PostharvestFacility:
    now = timezone.now()
    released = PostharvestFacility.objects.filter(pk=facility.pk, current_lot=lot).update(
        current_lot=None, occupied_since=None, version=F("version") + 1, updated_at=now
    )
    if not released:
        if not PostharvestFacility.objects.filter(pk=facility.pk).exists():
            raise FacilityNotFound()
        raise FacilityNotOccupiedByLot()
    facility.refresh_from_db()
    record_occupancy_event(
        facility=facility,
        actor=actor,
        action=PostharvestFacilityAuditEvent.Action.RELEASED,
        before_lot=lot,
        after_lot=None,
    )
    return facility


def _why_not_occupied(facility_id, kind: str) -> Exception:
    """El error exacto de una ocupación que no se aplicó, leyendo el elemento como quedó."""
    current = (
        PostharvestFacility.objects.select_related("current_lot").filter(pk=facility_id).first()
    )
    if current is None:
        return FacilityNotFound()
    if current.facility_type != kind:
        return FacilityWrongType()
    if not current.is_active:
        return FacilityUnavailable(FacilityStatus.INACTIVE)
    return FacilityUnavailable(FacilityStatus.OCCUPIED, current.current_lot)
