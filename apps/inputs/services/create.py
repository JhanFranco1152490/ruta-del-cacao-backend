from django.db import transaction

from apps.common.db import save_translating_unique
from apps.common.ownership import resolve_target_producer

from ..exceptions import DuplicateInput, ProducerInactive
from ..models import AgriculturalInput, AgriculturalInputAuditEvent
from .audit import record_input_audit_event

NAME_UNIQUE_CONSTRAINT = "inputs_input_producer_type_name_unique"
CONTENT_FIELDS = ("name", "input_type", "unit", "package_type", "package_size", "is_active")


def existing_duplicate(item: AgriculturalInput) -> AgriculturalInput | None:
    """El insumo del mismo productor con el mismo tipo y nombre normalizado, si lo hay."""
    return (
        AgriculturalInput.objects.filter(
            producer_id=item.producer_id,
            input_type=item.input_type,
            name_normalized=item.name_normalized,
        )
        .exclude(pk=item.pk)
        .first()
    )


def duplicate_error(item: AgriculturalInput) -> DuplicateInput:
    return DuplicateInput(existing_duplicate(item))


@transaction.atomic
def create_input(actor, data: dict) -> AgriculturalInput:
    """Registra un insumo en el catálogo del productor de la sesión, o del que nombra la cuenta
    técnica. Solo en línea: el servidor genera el `id`."""
    data = dict(data)
    producer_id = resolve_target_producer(
        actor,
        data,
        AgriculturalInput._meta.get_field("producer").related_model,
        inactive=ProducerInactive,
    )

    item = AgriculturalInput(producer_id=producer_id, **data)
    item.full_clean(validate_unique=False, validate_constraints=False)
    save_translating_unique(
        lambda: item.save(force_insert=True),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=lambda: duplicate_error(item),
    )
    record_input_audit_event(
        item=item,
        actor=actor,
        action=AgriculturalInputAuditEvent.Action.CREATED,
        changed_fields=CONTENT_FIELDS,
    )
    item.has_records = False
    return item
