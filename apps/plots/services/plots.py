from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.common.db import constraint_name

from ..exceptions import AreaMismatch, DuplicatePlotCode, InvalidBoundary, PlotIdConflict
from ..geometry import (
    Boundary,
    declared_area_matches,
    measured_area_hectares,
    stored_vertices,
    validate_boundary,
)
from ..models import Plot, PlotAuditEvent
from . import rules
from .audit import record_plot_audit_event

CODE_UNIQUE_CONSTRAINT = "plots_farm_code_normalized_unique"
# Lo que se guarda tal cual del cliente. `boundary` se valida y se convierte aparte, y `farm_id`
# fija la finca bloqueada.
WRITABLE_FIELDS = ("code", "area_hectares", "captured_at")


@transaction.atomic
def create_plot(actor, data: dict) -> tuple[Plot, bool]:
    """Registra una parcela en una finca del productor de la sesión. Devuelve `(parcela,
    creada)`.

    El cliente puede enviar el `id` que generó sin conexión. Reenviar el mismo `id` con el mismo
    contenido devuelve la parcela ya creada (`creada=False`), de modo que reintentar un envío
    cortado nunca duplica.
    """
    plot_id = data.get("id")
    if plot_id is not None and (existing := _existing(plot_id)) is not None:
        return _resent_plot(existing, actor, data), False

    farm = rules.lock_farm(actor, data["farm_id"])
    # Con la finca bloqueada, otra sincronización del mismo registro que llegó a la vez ya
    # terminó: si la creó, se responde como un reenvío.
    if plot_id is not None and (existing := _existing(plot_id)) is not None:
        return _resent_plot(existing, actor, data), False
    rules.ensure_farm_active(farm)

    plot = Plot(farm=farm, **_writable(data))
    if plot_id is not None:
        plot.pk = plot_id
    plot.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    boundary = _apply_boundary(plot, data.get("boundary"))
    rules.check_available_area(farm, plot.area_hectares)
    if boundary is not None:
        rules.check_no_overlap(farm, boundary)

    try:
        with transaction.atomic():
            plot.save(force_insert=True)
    except IntegrityError as error:
        # El mismo `id` en otra finca no pasa por el mismo bloqueo: el choque llega como clave
        # primaria repetida.
        existing = _existing(plot.pk) if plot_id is not None else None
        if existing is not None:
            return _resent_plot(existing, actor, data), False
        if constraint_name(error) == CODE_UNIQUE_CONSTRAINT:
            raise DuplicatePlotCode() from None
        raise
    record_plot_audit_event(plot=plot, actor=actor, action=PlotAuditEvent.Action.CREATED)
    return plot, True


def _apply_boundary(plot: Plot, vertices: list[dict] | None) -> Boundary | None:
    """Valida el contorno, calcula su área y la contrasta con la declarada. Sin contorno, la
    parcela queda sin área calculada."""
    if vertices is None:
        plot.boundary = None
        plot.measured_area_hectares = None
        return None
    boundary = validate_boundary(vertices)
    measured = measured_area_hectares(boundary.polygon)
    if not declared_area_matches(plot.area_hectares, measured):
        raise AreaMismatch(measured)
    plot.boundary = stored_vertices(boundary.vertices)
    plot.measured_area_hectares = measured
    return boundary


def _writable(data: dict) -> dict:
    return {name: data[name] for name in WRITABLE_FIELDS if name in data}


def _existing(plot_id) -> Plot | None:
    return Plot.objects.select_related("farm").filter(pk=plot_id).first()


def _resent_plot(existing: Plot, actor, data: dict) -> Plot:
    if existing.farm.producer_id != actor.producer_id:
        raise PlotIdConflict()
    # Con el mismo dueño, un contenido distinto suele ser un pendiente editado en el dispositivo
    # después de una creación cuya respuesta se perdió: el conflicto lleva la parcela del
    # servidor para que el cliente envíe esa edición con su versión.
    if not _same_content(existing, data):
        raise PlotIdConflict(existing)
    return existing


def _same_content(plot: Plot, data: dict) -> bool:
    # Se compara después de limpiar los datos como al guardarlos: "2.4" y "2.40", un código con
    # espacios alrededor o coordenadas escritas con más ceros no son contenido distinto.
    candidate = Plot(farm=plot.farm, **_writable(data))
    try:
        candidate.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
        boundary = data.get("boundary")
        if boundary is not None:
            boundary = stored_vertices(validate_boundary(boundary).vertices)
    except (ValidationError, InvalidBoundary):
        return False
    return (
        str(data["farm_id"]) == str(plot.farm_id)
        and candidate.code == plot.code
        and candidate.area_hectares == plot.area_hectares
        and _coordinates(boundary) == _coordinates(plot.boundary)
    )


def _coordinates(boundary: list[dict] | None):
    # Solo la forma: la hora o la precisión de un vértice pueden llegar distintas en un reintento
    # sin que el contorno cambie.
    if boundary is None:
        return None
    return [(vertex["latitude"], vertex["longitude"]) for vertex in boundary]
