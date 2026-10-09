from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.common.text import normalize_catalog_name
from apps.farms.tests.factories import FarmFactory
from apps.inputs.models import AgriculturalInput, InputMovement
from apps.producers.tests.factories import ProducerFactory


class AgriculturalInputFactory(DjangoModelFactory):
    class Meta:
        model = AgriculturalInput

    producer = factory.SubFactory(ProducerFactory)
    name = factory.Sequence(lambda n: f"Insumo {n:03d}")
    name_normalized = factory.LazyAttribute(lambda item: normalize_catalog_name(item.name))
    input_type = AgriculturalInput.InputType.FERTILIZER
    unit = AgriculturalInput.Unit.KG


def input_data(**overrides) -> dict:
    """Cuerpo válido de un alta, con los nombres de la API."""
    data = {"name": "Urea 46 %", "input_type": "fertilizer", "unit": "kg"}
    data.update(overrides)
    return data


class InputMovementFactory(DjangoModelFactory):
    """Un movimiento suelto, sin pasar por el servicio ni tocar las existencias."""

    class Meta:
        model = InputMovement

    input = factory.SubFactory(AgriculturalInputFactory)
    farm = factory.LazyAttribute(lambda movement: FarmFactory(producer=movement.input.producer))
    kind = InputMovement.Kind.ENTRY
    quantity = Decimal("100")
    occurred_on = factory.LazyFunction(timezone.localdate)
