from collections.abc import Iterable

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
    plantings: Iterable[tuple[CacaoVariety, dict]],
) -> PlotCharacterizationAuditEvent:
    """El evento lleva los valores de la ficha tras el cambio: con ellos, el historial muestra
    cuándo pasó la parcela de una etapa a otra o cuándo se renovó. La ficha no tiene datos
    personales, así que guardarlos no los repite."""
    return PlotCharacterizationAuditEvent.record(
        plot=characterization.plot,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        version=characterization.version,
        snapshot=snapshot(characterization, plantings),
    )


def snapshot(characterization: PlotCharacterization, plantings) -> dict:
    # El `id` además del nombre: si la variedad se renombra después, el historial sigue diciendo
    # cuál era.
    rows = sorted(
        (
            {
                "variety_id": str(variety.pk),
                "name": variety.name,
                "planting_date": row["planting_date"].strftime("%Y-%m"),
                "tree_count": row["tree_count"],
                "propagation": row["propagation"],
                "stage": row["stage"],
            }
            for variety, row in plantings
        ),
        key=lambda row: (row["name"], row["planting_date"], row["variety_id"]),
    )
    return {
        "plantings": rows,
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
