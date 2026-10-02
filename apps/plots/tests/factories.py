from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.common.text import normalize_name
from apps.farms.tests.factories import FarmFactory
from apps.plots.geometry import measured_area_hectares, stored_vertices, validate_boundary
from apps.plots.models import Plot

# Cerca de 7,8° de latitud, 0,001° son unos 110 m en cada eje.
LON = Decimal("-72.5")
LAT = Decimal("7.8")
STEP = Decimal("0.001")


def vertex(lon, lat, source="map", accuracy_m=None):
    return {
        "latitude": Decimal(lat),
        "longitude": Decimal(lon),
        "accuracy_m": accuracy_m,
        "captured_at": None,
        "source": source,
    }


def rect(x0, y0, x1, y1):
    """Rectángulo en pasos de STEP a partir de (LON, LAT)."""
    left, right = LON + STEP * Decimal(x0), LON + STEP * Decimal(x1)
    bottom, top = LAT + STEP * Decimal(y0), LAT + STEP * Decimal(y1)
    return [vertex(left, bottom), vertex(right, bottom), vertex(right, top), vertex(left, top)]


class PlotFactory(DjangoModelFactory):
    class Meta:
        model = Plot

    farm = factory.SubFactory(FarmFactory)
    code = factory.Sequence(lambda n: f"P-{n:02d}")
    code_normalized = factory.LazyAttribute(lambda plot: normalize_name(plot.code))
    area_hectares = Decimal("1.00")


def plot_data(farm, **overrides) -> dict:
    """Datos válidos de creación, con los nombres de campo del modelo."""
    data = {
        "farm_id": farm.pk,
        "code": "P1 · El Mango",
        "area_hectares": Decimal("1.00"),
        "boundary": None,
    }
    data.update(overrides)
    return data


def boundary_fields(vertices) -> dict:
    """`boundary` y `measured_area_hectares` como los guarda el servicio, para crear con la
    fábrica una parcela vecina ya dibujada."""
    boundary = validate_boundary(vertices)
    return {
        "boundary": stored_vertices(boundary.vertices),
        "measured_area_hectares": measured_area_hectares(boundary.polygon),
    }
