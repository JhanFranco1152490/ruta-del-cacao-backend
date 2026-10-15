import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.tests.factories import UserFactory
from apps.harvests.tests.factories import HarvestFactory
from apps.lots.models import Lot, LotCodeSequence
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db


def test_a_harvest_forms_a_single_lot():
    lot = LotFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        LotFactory(harvest=lot.harvest)


def test_the_code_is_unique():
    lot = LotFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        LotFactory(code=lot.code)


def test_a_harvest_with_a_lot_cannot_be_deleted():
    lot = LotFactory()

    with pytest.raises(ProtectedError):
        lot.harvest.delete()


def test_the_lot_is_found_from_its_harvest():
    lot = LotFactory()

    assert lot.harvest.lot == lot


def test_a_new_lot_is_generated():
    assert LotFactory().status == "generated"


def test_the_lot_survives_the_account_that_created_it():
    creator = UserFactory()
    lot = LotFactory(created_by=creator)

    creator.delete()

    lot.refresh_from_db()
    assert lot.created_by is None
    assert Lot.objects.count() == 1


def test_a_plot_has_one_sequence_per_harvest_date():
    harvest = HarvestFactory()
    LotCodeSequence.objects.create(plot=harvest.plot, harvest_date=harvest.harvest_date)

    with pytest.raises(IntegrityError), transaction.atomic():
        LotCodeSequence.objects.create(plot=harvest.plot, harvest_date=harvest.harvest_date)
