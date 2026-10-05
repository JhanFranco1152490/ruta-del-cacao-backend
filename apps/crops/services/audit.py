from collections.abc import Iterable
from datetime import date

from ..models import (
    CacaoVariety,
    CacaoVarietyAuditEvent,
    PlotCharacterization,
    PlotCharacterizationAuditEvent,
)


def record_characterization_audit_event(
    *,
    characterization: PlotCharacterization,
    actor,
    action: str,
    changed_fields: Iterable[str],
    rows: Iterable[tuple[CacaoVariety, date, int]],
) -> PlotCharacterizationAuditEvent:
    """El evento lleva los valores de la ficha tras el cambio: con ellos, el historial muestra
    cuándo pasó la parcela de una etapa a otra o cuándo se renovó. La ficha no tiene datos
    personales, así que guardarlos no los repite."""
    return PlotCharacterizationAuditEvent.record(
        plot=characterization.plot,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        snapshot=snapshot(characterization, rows),
    )


def snapshot(characterization: PlotCharacterization, rows) -> dict:
    # El `id` además del nombre: si la variedad se renombra después, el historial sigue diciendo
    # cuál era.
    plantings = sorted(
        (
            {
                "variety_id": str(variety.pk),
                "name": variety.name,
                "planting_date": planting_date.strftime("%Y-%m"),
                "tree_count": tree_count,
            }
            for variety, planting_date, tree_count in rows
        ),
        key=lambda row: (row["name"], row["planting_date"], row["variety_id"]),
    )
    return {
        "plantings": plantings,
        "stage": characterization.stage,
        "management_system": characterization.management_system,
        "shade_type": characterization.shade_type,
    }


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
