"""Geometría del contorno de una parcela: forma válida, área, superposición y ajuste sugerido.

Un contorno es una lista de vértices (`latitude`, `longitude`, `accuracy_m`, `captured_at`,
`source`) en orden y sin repetir el primero al final. Las operaciones se hacen sobre
`(longitud, latitud)` en grados: las parcelas miden pocas hectáreas, así que tratar los grados
como un plano no cambia qué se cruza ni qué se superpone; las áreas sí se miden en la esfera.
"""

from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from shapely import Polygon, unary_union
from shapely.geometry.base import BaseGeometry

from apps.common.geo import ring_area_m2
from apps.common.validators import validate_latitude, validate_longitude

from .exceptions import InvalidBoundary

MIN_VERTICES = 3
MAX_VERTICES = 100
# El servidor guarda y compara coordenadas con 7 decimales (unos 1,1 cm).
COORDINATE_STEP = Decimal("0.0000001")
AREA_STEP = Decimal("0.0001")
SQUARE_METRES_PER_HECTARE = 10_000
# Una intersección menor que esto se trata como un lindero compartido: absorbe el redondeo de
# las coordenadas y el ruido de dos dibujos que se tocan.
OVERLAP_TOLERANCE_M2 = 1.0
# Diferencia máxima entre el área declarada y la del dibujo, relativa a la del dibujo.
AREA_TOLERANCE = Decimal("0.05")
ADJUSTED_SOURCE = "adjusted"


@dataclass(frozen=True)
class Boundary:
    vertices: list[dict]
    polygon: Polygon


@dataclass(frozen=True)
class Overlap:
    key: Hashable
    area_hectares: Decimal


def validate_boundary(vertices: list[dict]) -> Boundary:
    """Normaliza las coordenadas a 7 decimales y comprueba que formen un polígono simple."""
    if len(vertices) < MIN_VERTICES:
        raise InvalidBoundary(f"debe tener al menos {MIN_VERTICES} vértices")
    if len(vertices) > MAX_VERTICES:
        raise InvalidBoundary(f"no puede tener más de {MAX_VERTICES} vértices")

    normalized = [_normalized_vertex(vertex) for vertex in vertices]
    points = [_point(vertex) for vertex in normalized]
    if len(set(points)) < len(points):
        raise InvalidBoundary("tiene vértices repetidos")

    polygon = Polygon(points)
    # Se mira la envolvente y no el área del polígono: dos lados cruzados en forma de moño
    # también dan área neta 0, porque sus dos mitades se restan, y ese es otro error.
    if polygon.convex_hull.area == 0:
        raise InvalidBoundary("no encierra ningún área")
    if not polygon.is_valid:
        raise InvalidBoundary("sus lados se cruzan")
    return Boundary(vertices=normalized, polygon=polygon)


def stored_vertices(vertices: list[dict]) -> list[dict]:
    """El contorno validado tal como se guarda en el JSON de la parcela: las coordenadas como
    texto con 7 decimales (un número JSON podría perder precisión) y solo los campos conocidos."""
    return [
        {
            "latitude": str(vertex["latitude"]),
            "longitude": str(vertex["longitude"]),
            "accuracy_m": _text_or_none(vertex.get("accuracy_m")),
            "captured_at": _text_or_none(vertex.get("captured_at")),
            "source": vertex["source"],
        }
        for vertex in vertices
    ]


def to_polygon(vertices: list[dict]) -> Polygon:
    """El polígono de un contorno ya validado y guardado."""
    return Polygon([_point(vertex) for vertex in vertices])


def measured_area_hectares(geometry: BaseGeometry) -> Decimal:
    return _hectares(_area_m2(geometry))


def declared_area_matches(declared: Decimal, measured: Decimal) -> bool:
    return abs(declared - measured) <= AREA_TOLERANCE * measured


def find_overlaps(polygon: Polygon, neighbours: dict[Hashable, Polygon]) -> list[Overlap]:
    """Las vecinas que el polígono invade, en el orden recibido, con el área invadida."""
    overlaps = []
    for key, neighbour in neighbours.items():
        area_m2 = _area_m2(polygon.intersection(neighbour))
        if area_m2 >= OVERLAP_TOLERANCE_M2:
            overlaps.append(Overlap(key=key, area_hectares=_hectares(area_m2)))
    return overlaps


def suggest_boundary(boundary: Boundary, neighbours: list[Polygon]) -> list[dict] | None:
    """El contorno propio sin la parte que cae dentro de las vecinas, o `None` si no queda un
    solo polígono sin huecos que sugerir (la parcela queda entera dentro de otra, o el recorte la
    parte en varios pedazos o le abre un hueco).

    Los vértices que ya estaban en el contorno conservan sus datos; los nuevos (movidos al borde
    de la vecina o en el cruce de los dos bordes) se marcan como ajustados.
    """
    remainder = boundary.polygon.difference(unary_union(neighbours))
    pieces = [piece for piece in _polygons(remainder) if _area_m2(piece) >= OVERLAP_TOLERANCE_M2]
    if len(pieces) != 1 or any(
        ring_area_m2(interior.coords[:-1]) >= OVERLAP_TOLERANCE_M2
        for interior in pieces[0].interiors
    ):
        return None

    originals = {_point(vertex): vertex for vertex in boundary.vertices}
    suggestion = []
    for longitude, latitude in pieces[0].simplify(0).exterior.coords[:-1]:
        vertex = {
            "latitude": _coordinate(latitude),
            "longitude": _coordinate(longitude),
            "accuracy_m": None,
            "captured_at": None,
            "source": ADJUSTED_SOURCE,
        }
        point = _point(vertex)
        if suggestion and _point(suggestion[-1]) == point:
            continue
        suggestion.append(originals.get(point, vertex))

    try:
        return validate_boundary(suggestion).vertices
    except InvalidBoundary:
        # Al redondear a 7 decimales un recorte muy fino puede quedar mal formado: es mejor no
        # sugerir nada que sugerir un polígono que el propio servidor rechazaría.
        return None


def _normalized_vertex(vertex: dict) -> dict:
    latitude = Decimal(vertex["latitude"])
    longitude = Decimal(vertex["longitude"])
    try:
        validate_latitude(latitude)
        validate_longitude(longitude)
    except ValidationError:
        raise InvalidBoundary("tiene vértices con coordenadas fuera de rango") from None
    return {**vertex, "latitude": _coordinate(latitude), "longitude": _coordinate(longitude)}


def _coordinate(value) -> Decimal:
    # `repr` de un float es el decimal más corto que lo representa: así -72.499 vuelve como
    # -72.499 y no como -72.49899999999999...
    decimal = value if isinstance(value, Decimal) else Decimal(repr(value))
    return decimal.quantize(COORDINATE_STEP, rounding=ROUND_HALF_UP)


def _text_or_none(value) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _point(vertex: dict) -> tuple[float, float]:
    return (float(vertex["longitude"]), float(vertex["latitude"]))


def _polygons(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [] if geometry.is_empty else [geometry]
    return [polygon for part in getattr(geometry, "geoms", ()) for polygon in _polygons(part)]


def _area_m2(geometry: BaseGeometry) -> float:
    return sum(
        ring_area_m2(polygon.exterior.coords[:-1])
        - sum(ring_area_m2(interior.coords[:-1]) for interior in polygon.interiors)
        for polygon in _polygons(geometry)
    )


def _hectares(area_m2: float) -> Decimal:
    return (Decimal(repr(area_m2)) / SQUARE_METRES_PER_HECTARE).quantize(
        AREA_STEP, rounding=ROUND_HALF_UP
    )
