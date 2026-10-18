from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.tests.factories import UserFactory
from apps.harvests.models import Harvest
from apps.harvests.tests.factories import HarvestFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("weight", [Decimal("0"), Decimal("-1.5")])
def test_the_weight_must_be_positive_in_the_database(weight):
    with pytest.raises(IntegrityError), transaction.atomic():
        HarvestFactory(green_weight_kg=weight)


def test_the_weight_keeps_a_single_decimal():
    harvest = HarvestFactory(green_weight_kg=Decimal("120.5"))

    harvest.refresh_from_db()

    assert harvest.green_weight_kg == Decimal("120.5")


def test_a_plot_with_harvests_cannot_be_deleted():
    harvest = HarvestFactory()

    with pytest.raises(ProtectedError):
        harvest.plot.delete()


def test_a_harvested_variety_cannot_be_deleted():
    harvest = HarvestFactory()

    with pytest.raises(ProtectedError):
        harvest.variety.delete()


def test_a_collector_cannot_be_deleted():
    harvest = HarvestFactory()

    with pytest.raises(ProtectedError):
        harvest.collector.delete()


def test_the_harvest_survives_the_account_that_registered_it():
    registrar = UserFactory()
    harvest = HarvestFactory(registered_by=registrar)

    registrar.delete()

    harvest.refresh_from_db()
    assert harvest.registered_by is None


def test_harvests_come_most_recent_first():
    first = HarvestFactory(harvest_date=date(2026, 10, 1))
    HarvestFactory(plot=first.plot, harvest_date=date(2026, 10, 20))

    assert [harvest.harvest_date.day for harvest in Harvest.objects.all()] == [20, 1]
