from django.db import transaction

from apps.common.db import save_translating_unique

from ..exceptions import DuplicateFacilityName
from ..models import PostharvestFacility, PostharvestFacilityAuditEvent
from .audit import record_facility_audit_event
from .farms import ensure_farm_active, ensure_has_a_farm, lock_farm

NAME_UNIQUE_CONSTRAINT = "facilities_facility_farm_name_unique"
CONTENT_FIELDS = ("facility_type", "name", "capacity_kg", "is_active")


def existing_duplicate(facility: PostharvestFacility) -> PostharvestFacility | None:
    """El elemento de la misma finca con el mismo nombre normalizado, si lo hay."""
    return (
        PostharvestFacility.objects.filter(
            farm_id=facility.farm_id, name_normalized=facility.name_normalized
        )
        .exclude(pk=facility.pk)
        .first()
    )


def duplicate_error(facility: PostharvestFacility) -> DuplicateFacilityName:
    return DuplicateFacilityName(existing_duplicate(facility))


@transaction.atomic
def create_facility(actor, data: dict) -> PostharvestFacility:
    """Registra un cajón o una marquesina en una finca que `actor` alcanza. Queda Disponible.
    Solo en línea: el servidor genera el `id`."""
    ensure_has_a_farm(actor)
    data = dict(data)
    farm = lock_farm(actor, data.pop("farm_id"))
    ensure_farm_active(farm)

    facility = PostharvestFacility(farm=farm, created_by=actor, **data)
    facility.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    save_translating_unique(
        lambda: facility.save(force_insert=True),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=lambda: duplicate_error(facility),
    )
    record_facility_audit_event(
        facility=facility,
        actor=actor,
        action=PostharvestFacilityAuditEvent.Action.CREATED,
        changed_fields=CONTENT_FIELDS,
    )
    facility.has_records = False
    return facility
