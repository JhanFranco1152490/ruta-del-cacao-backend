from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.common.text import normalize_name
from apps.farms.models import Farm
from apps.producers.tests.factories import ProducerFactory


class FarmFactory(DjangoModelFactory):
    class Meta:
        model = Farm

    producer = factory.SubFactory(ProducerFactory)
    name = factory.Sequence(lambda n: f"Finca {n:03d}")
    name_normalized = factory.LazyAttribute(lambda farm: normalize_name(farm.name))
    department_code = "54"
    municipality_code = "54001"
    area_hectares = Decimal("12.50")
    altitude_masl = 950
    latitude = Decimal("7.8234567")
    longitude = Decimal("-72.5123456")


def farm_data(**overrides) -> dict:
    """Datos válidos de creación, con los nombres de campo del modelo."""
    data = {
        "name": "La Esperanza",
        "department_code": "54",
        "municipality_code": "54001",
        "details": "Vereda El Pórtico, km 4",
        "area_hectares": Decimal("12.50"),
        "altitude_masl": 950,
        "latitude": Decimal("7.8234567"),
        "longitude": Decimal("-72.5123456"),
    }
    data.update(overrides)
    return data
