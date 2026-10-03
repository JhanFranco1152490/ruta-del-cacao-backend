import math
from collections.abc import Sequence

# Radio medio de la Tierra que usa la misma fórmula en el frontend al dibujar. Si uno de los dos
# lados lo cambia, el área que ve la persona deja de coincidir con la que valida el servidor.
EARTH_RADIUS_M = 6371008.8
_FACTOR = EARTH_RADIUS_M * EARTH_RADIUS_M / 2
_RADIANS = math.pi / 180


def ring_area_m2(ring: Sequence[tuple[float, float]]) -> float:
    """Área en m² de un anillo de puntos `(longitud, latitud)`, sin repetir el primero al final.

    Es la fórmula esférica de Chamberlain y Duquette (la de `@turf/area`), con las mismas
    operaciones y en el mismo orden para que dé exactamente el mismo número. Para parcelas de
    pocas hectáreas, su diferencia con un cálculo sobre el elipsoide es mucho menor que el error
    del GPS.
    """
    count = len(ring)
    if count < 3:
        return 0.0
    total = 0.0
    for index in range(count):
        lower = ring[index]
        middle = ring[(index + 1) % count]
        upper = ring[(index + 2) % count]
        total += (upper[0] * _RADIANS - lower[0] * _RADIANS) * math.sin(middle[1] * _RADIANS)
    return abs(total * _FACTOR)


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia en metros entre dos puntos `(longitud, latitud)`, por la fórmula de haversine
    sobre la misma esfera del cálculo de áreas: la medición es la misma en el dispositivo."""
    lon_a, lat_a = (value * _RADIANS for value in a)
    lon_b, lat_b = (value * _RADIANS for value in b)
    # Orden de las operaciones como en `@turf/distance`, para que dé el mismo número.
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    haversine = math.sin(delta_lat / 2) ** 2 + math.sin(delta_lon / 2) ** 2 * math.cos(
        lat_a
    ) * math.cos(lat_b)
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
