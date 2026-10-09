import factory
from factory.django import DjangoModelFactory

from apps.common.text import normalize_catalog_name
from apps.inputs.models import AgriculturalInput
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
