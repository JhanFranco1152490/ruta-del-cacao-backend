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
