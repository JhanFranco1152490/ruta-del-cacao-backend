from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from ..exceptions import (
    DensityTooHigh,
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
    PlotPlanting,
)
from .audit import record_characterization_audit_event
from .content import SCALAR_FIELDS, changed_fields
from .locks import lock_plot
from .queries import with_rows

# 1 m² por árbol: ningún cacaotal llega ahí (las siembras intensivas rondan 2.500 árboles/ha). No
# bloquea un caso real y sí el cero de más, que solo con un aviso llegaría al servidor desde la
# cola sin conexión.
MAX_TREES_PER_HECTARE = 10_000


@transaction.atomic
def save_characterization(
    actor, plot_id, expected_version: int | None, data: dict
) -> tuple[PlotCharacterization, bool]:
    """Registra o reemplaza la ficha completa de la parcela, con sus siembras y su evento en el
    historial. Devuelve la ficha y si se creó.

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

    # El bloqueo de la parcela basta: todo guardado de su ficha lo toma antes de leerla. Con sus
    # siembras cargadas, porque un conflicto la devuelve entera en `current`.
    current = with_rows(PlotCharacterization.objects.filter(plot=plot)).first()
    changes = changed_fields(current, data) if current is not None else None
    if changes == []:
        return current, False
    if expected_version != (current.version if current is not None else None):
        raise StaleCharacterizationVersion(current)

    varieties = _check_varieties(data, current)
    _check_density(plot, data)
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

    characterization.plantings.all().delete()
    PlotPlanting.objects.bulk_create(
        PlotPlanting(
            characterization=characterization,
            variety=varieties[row["variety_id"]],
            planting_date=row["planting_date"],
            tree_count=row["tree_count"],
            propagation=row["propagation"],
            stage=row["stage"],
        )
        for row in data["plantings"]
    )
    # Las siembras leídas antes del reemplazo ya no existen: quien reciba la ficha debe ver las
    # nuevas.
    getattr(characterization, "_prefetched_objects_cache", {}).pop("plantings", None)
    record_characterization_audit_event(
        characterization=characterization,
        actor=actor,
        action=action,
        changed_fields=changes or (),
        plantings=[(varieties[row["variety_id"]], row) for row in data["plantings"]],
    )
    return characterization, current is None


def _check_varieties(data: dict, current: PlotCharacterization | None) -> dict:
    """Las variedades pedidas, por `id`. Todas deben existir, y una desactivada solo se acepta
    si ya estaba en la ficha: desactivar una variedad deja de ofrecerla para siembras nuevas,
    no borra los árboles que ya están sembrados, y a sus siembras se les pueden corregir los
    árboles.
    """
    ids = [row["variety_id"] for row in data["plantings"]]
    varieties = CacaoVariety.objects.in_bulk(ids)
    if len(varieties) != len(set(ids)):
        raise UnknownVariety()

    already_there = (
        {row.variety_id for row in current.plantings.all()} if current is not None else set()
    )
    retired = sorted(
        variety.name
        for variety in varieties.values()
        if not variety.is_active and variety.pk not in already_there
    )
    if retired:
        raise VarietyInactive(retired)
    return varieties


def _check_density(plot, data: dict) -> None:
    """Contra el área declarada de la parcela en este momento, la misma con la que la interfaz
    calcula la densidad."""
    trees = sum(row["tree_count"] for row in data["plantings"])
    if trees > MAX_TREES_PER_HECTARE * plot.area_hectares:
        density = (Decimal(trees) / plot.area_hectares).quantize(0, rounding=ROUND_HALF_UP)
        raise DensityTooHigh(int(density), MAX_TREES_PER_HECTARE)
