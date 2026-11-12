import uuid

import pytest

from apps.common.contracts.reports import ScopedLot, report_source
from apps.farms.models import Farm
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db


def lot_in_scope(farms, lot_id):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("lot_in_scope")(farm_ids, lot_id)


def test_a_lot_of_the_scope_comes_with_its_code_plot_and_farm(django_assert_num_queries):
    lot = LotFactory()
    plot = lot.harvest.plot

    with django_assert_num_queries(1):
        found = lot_in_scope([plot.farm], lot.pk)

    assert found == ScopedLot(lot_id=lot.pk, farm_id=plot.farm_id, plot_id=plot.pk, code=lot.code)


def test_a_lot_of_another_farm_is_not_in_the_scope():
    lot = LotFactory()
    other = LotFactory()

    assert lot_in_scope([other.harvest.plot.farm], lot.pk) is None


def test_a_lot_that_does_not_exist_is_not_in_the_scope():
    lot = LotFactory()

    assert lot_in_scope([lot.harvest.plot.farm], uuid.uuid4()) is None
