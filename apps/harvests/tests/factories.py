from datetime import date
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.crops.tests.factories import (
    CacaoVarietyFactory,
    PlotCharacterizationFactory,
    PlotPlantingFactory,
)
from apps.harvests.models import Harvest
from apps.plots.tests.factories import PlotFactory


def characterized_plot(variety=None, planting_date=date(2021, 3, 1), **plot_fields):
    """Una parcela con ficha y una siembra de `variedad`: lo mínimo para poder cosecharla."""
    plot = PlotFactory(**plot_fields)
    characterization = PlotCharacterizationFactory(plot=plot)
    PlotPlantingFactory(
        characterization=characterization,
        variety=variety or CacaoVarietyFactory(),
        planting_date=planting_date,
    )
    return plot


class HarvestFactory(DjangoModelFactory):
    class Meta:
        model = Harvest

    plot = factory.LazyFunction(characterized_plot)
    harvest_date = date(2026, 10, 14)
    green_weight_kg = Decimal("120.5")
    # La variedad de la primera siembra de la parcela: una cosecha válida cosecha lo que se sembró.
    variety = factory.LazyAttribute(
        lambda harvest: harvest.plot.characterization.plantings.first().variety
    )
    # El recolector es siempre una cuenta del mismo productor de la parcela.
    collector = factory.SubFactory(
        UserFactory, producer=factory.SelfAttribute("..plot.farm.producer")
    )
    characterization_version = 1
