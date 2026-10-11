from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.activities.models import AgriculturalActivityInput
from apps.activities.tests.factories import AgriculturalActivityInputFactory, done_activity
from apps.inputs.exceptions import InputHasRecords, InputUnitLocked
from apps.inputs.services import delete_input, get_input, update_input
from apps.inputs.tests.factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


def test_a_used_input_is_kept_with_its_quantity_and_its_stock_movement():
    used = AgriculturalActivityInputFactory(quantity=Decimal("2.5"))

    stored = AgriculturalActivityInput.objects.get(pk=used.pk)
    assert stored.quantity == Decimal("2.500")
    assert stored.stock_movement.quantity == Decimal("-2.500")
    assert list(stored.activity.inputs.all()) == [stored]


def test_the_quantity_must_be_greater_than_zero():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityInputFactory(quantity=Decimal("0"))


def test_an_input_is_not_repeated_in_the_same_activity():
    used = AgriculturalActivityInputFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityInputFactory(activity=used.activity, input=used.input)


def test_a_stock_movement_belongs_to_a_single_used_input():
    used = AgriculturalActivityInputFactory()
    other_activity = done_activity(plot=used.activity.plot)

    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityInputFactory(
            activity=other_activity, input=used.input, stock_movement=used.stock_movement
        )


def test_an_input_used_by_an_activity_has_records_and_is_protected():
    # Solo con la relación: la app de insumos no sabe nada de las actividades.
    used = AgriculturalActivityInputFactory()
    member = UserFactory(producer=used.input.producer)

    assert get_input(member, used.input.pk).has_records is True
    with pytest.raises(InputUnitLocked):
        update_input(member, used.input.pk, 1, {"unit": "g"})
    with pytest.raises(InputHasRecords):
        delete_input(member, used.input.pk, 1)


def test_an_input_nobody_used_is_still_free():
    item = AgriculturalInputFactory()
    member = UserFactory(producer=item.producer)

    assert get_input(member, item.pk).has_records is False
