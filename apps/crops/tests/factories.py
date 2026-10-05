from datetime import date

import factory
from factory.django import DjangoModelFactory

from apps.crops.choices import Stage
from apps.crops.models import CacaoVariety, PlotCharacterization, PlotPlanting, search_text
from apps.crops.text import normalize_variety_name
from apps.plots.tests.factories import PlotFactory


class CacaoVarietyFactory(DjangoModelFactory):
    class Meta:
        model = CacaoVariety

    # Nombres que no existen en el catálogo inicial, para no chocar con él.
    name = factory.Sequence(lambda n: f"Clon de prueba {n:03d}")
    name_normalized = factory.LazyAttribute(lambda variety: normalize_variety_name(variety.name))
    common_names = factory.LazyFunction(list)
    search_normalized = factory.LazyAttribute(
        lambda variety: search_text(variety.name, variety.common_names)
    )


class PlotCharacterizationFactory(DjangoModelFactory):
    class Meta:
        model = PlotCharacterization

    plot = factory.SubFactory(PlotFactory)
    stage = Stage.FULL_PRODUCTION


class PlotPlantingFactory(DjangoModelFactory):
    class Meta:
        model = PlotPlanting

    characterization = factory.SubFactory(PlotCharacterizationFactory)
    variety = factory.SubFactory(CacaoVarietyFactory)
    planting_date = date(2021, 3, 1)
    tree_count = 600
