from django.db import transaction

from ..exceptions import (
    FarmInactive,
    PlotInactive,
    StaleCharacterizationVersion,
    UnknownVariety,
    VarietyInactive,
)
from ..models import (
    CacaoVariety,
    PlotCharacterization,
    PlotCharacterizationAuditEvent,
    PlotCharacterizationVariety,
)
from .audit import record_characterization_audit_event
from .content import SCALAR_FIELDS, changed_fields
from .locks import lock_plot


@transaction.atomic
def save_characterization(
    actor, plot_id, expected_version: int | None, data: dict
) -> tuple[PlotCharacterization, bool]:
    """Registra o reemplaza la ficha completa de la parcela, con sus filas de variedades y su
    evento en el historial. Devuelve la ficha y si se creó.

    `expected_version` es `None` para registrar y la versión que se leyó para editar. Si la
    ficha ya tiene exactamente lo que se pide, se devuelve tal cual aunque la versión no
    coincida: es una cola sin conexión que reintenta porque no recibió la respuesta.
    """
    plot = lock_plot(actor, plot_id)
    # Con la finca o la parcela inactivas, la ficha queda congelada como el resto de la parcela.
    if not plot.farm.is_active:
        raise FarmInactive()
    if not plot.is_active:
        raise PlotInactive()

    # El bloqueo de la parcela basta: todo guardado de su ficha lo toma antes de leerla.
    current = PlotCharacterization.objects.filter(plot=plot).prefetch_related("varieties").first()
    changes = changed_fields(current, data) if current is not None else None
    if changes == []:
        return current, False
    if expected_version != (current.version if current is not None else None):
        raise StaleCharacterizationVersion(current)

    varieties = _check_varieties(data, current)
    if current is None:
        characterization = PlotCharacterization(plot=plot)
        action = PlotCharacterizationAuditEvent.Action.CREATED
    else:
        characterization = current
        characterization.version += 1
        action = PlotCharacterizationAuditEvent.Action.UPDATED
    for name in SCALAR_FIELDS:
        setattr(characterization, name, data.get(name))
    characterization.captured_at = data.get("captured_at")
    # Su clave es la parcela, que no tiene valor por defecto: sin `force_insert`, Django
    # intentaría primero un UPDATE de una fila que todavía no existe.
    characterization.save(force_insert=current is None)

    characterization.varieties.all().delete()
    PlotCharacterizationVariety.objects.bulk_create(
        PlotCharacterizationVariety(
            characterization=characterization,
            variety=varieties[row["variety_id"]],
            tree_count=row["tree_count"],
        )
        for row in data["varieties"]
    )
    # Las filas leídas antes del reemplazo ya no existen: quien reciba la ficha debe ver las
    # nuevas.
    getattr(characterization, "_prefetched_objects_cache", {}).pop("varieties", None)
    record_characterization_audit_event(
        characterization=characterization,
        actor=actor,
        action=action,
        changed_fields=changes or (),
        rows=[(varieties[row["variety_id"]], row["tree_count"]) for row in data["varieties"]],
    )
    return characterization, current is None


def _check_varieties(data: dict, current: PlotCharacterization | None) -> dict:
    """Las variedades pedidas, por `id`. Todas deben existir, y una desactivada solo se acepta
    si ya estaba en la ficha: desactivar una variedad deja de ofrecerla para siembras nuevas,
    no borra los árboles que ya están sembrados, y a su fila se le pueden corregir los árboles.
    """
    ids = [row["variety_id"] for row in data["varieties"]]
    varieties = CacaoVariety.objects.in_bulk(ids)
    if len(varieties) != len(set(ids)):
        raise UnknownVariety()

    already_there = (
        {row.variety_id for row in current.varieties.all()} if current is not None else set()
    )
    retired = sorted(
        variety.name
        for variety in varieties.values()
        if not variety.is_active and variety.pk not in already_there
    )
    if retired:
        raise VarietyInactive(retired)
    return varieties
