"""Cómo se convierten y se comparan los datos de una parcela, en el alta y en la edición."""

from django.core.exceptions import ValidationError

from ..exceptions import AreaMismatch, InvalidBoundary
from ..geometry import (
    Boundary,
    declared_area_matches,
    measured_area_hectares,
    stored_vertices,
    to_polygon,
    validate_boundary,
)
from ..models import Plot

CODE_UNIQUE_CONSTRAINT = "plots_farm_code_normalized_unique"
# Lo que se guarda tal cual del cliente al crear. `boundary` se valida y se convierte aparte, y
# `farm_id` fija la finca bloqueada.
WRITABLE_FIELDS = ("code", "area_hectares", "captured_at")
# Lo que acepta una edición. `farm_id` no está: una parcela no cambia de finca.
UPDATABLE_FIELDS = ("code", "area_hectares", "is_active")


def apply_boundary(plot: Plot, vertices: list[dict] | None) -> Boundary | None:
    """Valida el contorno, calcula su área y la contrasta con la declarada. Sin contorno, la
    parcela queda sin área calculada."""
    if vertices is None:
        plot.boundary = None
        plot.measured_area_hectares = None
        return None
    boundary = validate_boundary(vertices)
    measured = measured_area_hectares(boundary.polygon)
    check_declared_area(plot, measured)
    plot.boundary = stored_vertices(boundary.vertices)
    plot.measured_area_hectares = measured
    return boundary


def check_declared_area(plot: Plot, measured) -> None:
    if not declared_area_matches(plot.area_hectares, measured):
        raise AreaMismatch(measured)


def current_boundary(plot: Plot) -> Boundary | None:
    if plot.boundary is None:
        return None
    return Boundary(vertices=plot.boundary, polygon=to_polygon(plot.boundary))


def writable(data: dict) -> dict:
    return {name: data[name] for name in WRITABLE_FIELDS if name in data}


def matches(plot: Plot, data: dict, fields) -> bool:
    """Si la parcela ya tiene, en `fields`, lo que piden los datos.

    Se compara después de limpiar los datos como al guardarlos: "2.4" y "2.40", un código con
    espacios alrededor o coordenadas escritas con más ceros no son contenido distinto.
    """
    candidate = Plot(
        farm=plot.farm, code=plot.code, area_hectares=plot.area_hectares, is_active=plot.is_active
    )
    for name in (*WRITABLE_FIELDS, *UPDATABLE_FIELDS):
        if name in data:
            setattr(candidate, name, data[name])
    try:
        candidate.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
        boundary = data.get("boundary")
        if boundary is not None:
            boundary = stored_vertices(validate_boundary(boundary).vertices)
    except (ValidationError, InvalidBoundary):
        return False
    for name in fields:
        if name == "boundary":
            if coordinates(boundary) != coordinates(plot.boundary):
                return False
        elif name in UPDATABLE_FIELDS and getattr(candidate, name) != getattr(plot, name):
            return False
    return True


def coordinates(boundary: list[dict] | None):
    # Solo la forma: la hora o la precisión de un vértice pueden llegar distintas en un reintento
    # sin que el contorno cambie.
    if boundary is None:
        return None
    return [(vertex["latitude"], vertex["longitude"]) for vertex in boundary]
