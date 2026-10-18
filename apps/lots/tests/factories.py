import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.harvests.tests.factories import HarvestFactory
from apps.lots.code import build_lot_code
from apps.lots.models import Lot


class LotFactory(DjangoModelFactory):
    """Un lote ya conformado, con el código que le tocaría. El consecutivo es propio de la
    fábrica: para probar la asignación real se usa el servicio."""

    class Meta:
        model = Lot

    harvest = factory.SubFactory(HarvestFactory)
    created_by = factory.SubFactory(
        UserFactory, producer=factory.SelfAttribute("..harvest.plot.farm.producer")
    )
    code = factory.LazyAttributeSequence(
        lambda lot, n: build_lot_code(
            lot.harvest.plot.farm.producer.member_code,
            lot.harvest.plot.farm.number,
            lot.harvest.plot.number,
            lot.harvest.harvest_date,
            n + 1,
        )
    )
