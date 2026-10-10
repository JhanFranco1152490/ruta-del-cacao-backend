from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.farms.tests.factories import FarmFactory
from apps.inputs.models import InputMovement, InputStock

from .factories import AgriculturalInputFactory, InputMovementFactory

pytestmark = pytest.mark.django_db


def make(**fields):
    return InputMovementFactory(**fields)


def test_an_entry_must_be_positive():
    for quantity in ("0", "-5"):
        with pytest.raises(IntegrityError), transaction.atomic():
            make(kind="entry", quantity=Decimal(quantity))


def test_a_consumption_must_be_negative():
    for quantity in ("0", "5"):
        with pytest.raises(IntegrityError), transaction.atomic():
            make(kind="consumption", quantity=Decimal(quantity))
    make(kind="consumption", quantity=Decimal("-5"))


def test_a_count_needs_the_counted_quantity_and_the_others_cannot_have_it():
    with pytest.raises(IntegrityError), transaction.atomic():
        make(kind="count", quantity=Decimal("-20"))
    with pytest.raises(IntegrityError), transaction.atomic():
        make(kind="count", quantity=Decimal("0"), counted_quantity=Decimal("-1"))
    with pytest.raises(IntegrityError), transaction.atomic():
        make(kind="entry", counted_quantity=Decimal("10"))
    make(kind="count", quantity=Decimal("0"), counted_quantity=Decimal("0"))


def test_a_count_can_leave_a_difference_of_any_sign():
    make(kind="count", quantity=Decimal("-20"), counted_quantity=Decimal("230"))
    make(kind="count", quantity=Decimal("40"), counted_quantity=Decimal("290"))


def test_there_is_one_stock_per_input_and_farm():
    item = AgriculturalInputFactory()
    farm = FarmFactory(producer=item.producer)
    InputStock.objects.create(input=item, farm=farm)

    with pytest.raises(IntegrityError), transaction.atomic():
        InputStock.objects.create(input=item, farm=farm)
    InputStock.objects.create(input=item, farm=FarmFactory(producer=item.producer))


def test_the_movement_survives_the_account_that_registered_it():
    from apps.accounts.tests.factories import UserFactory

    actor = UserFactory()
    movement = make(actor=actor)

    actor.delete()

    movement.refresh_from_db()
    assert movement.actor is None


def test_movements_come_from_the_newest_to_the_oldest():
    item = AgriculturalInputFactory()
    farm = FarmFactory(producer=item.producer)
    today = timezone.localdate()
    old = make(input=item, farm=farm, occurred_on=today - timezone.timedelta(days=3))
    new = make(input=item, farm=farm, occurred_on=today)

    assert list(InputMovement.objects.filter(input=item)) == [new, old]
