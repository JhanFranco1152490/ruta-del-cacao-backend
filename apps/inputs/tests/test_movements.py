import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.inputs.exceptions import (
    FarmInactive,
    FarmNotFound,
    InputInactive,
    InputNotFound,
    MovementIdConflict,
)
from apps.inputs.models import InputMovement, InputStock
from apps.inputs.services import record_consumption, register_movement
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def item(producer):
    return AgriculturalInputFactory(producer=producer, unit="ml")


def entry(item, farm, amount="300", **overrides):
    data = {
        "input_id": item.pk,
        "farm_id": farm.pk,
        "kind": "entry",
        "quantity": Decimal(amount),
        "occurred_on": TODAY,
    }
    data.update(overrides)
    return data


def count(item, farm, amount="230", **overrides):
    data = {
        "input_id": item.pk,
        "farm_id": farm.pk,
        "kind": "count",
        "counted_quantity": Decimal(amount),
        "occurred_on": TODAY,
    }
    data.update(overrides)
    return data


def stock_of(item, farm):
    return InputStock.objects.get(input=item, farm=farm)


def test_an_entry_creates_the_stock_with_the_first_movement(member, item, farm):
    movement, stock, created = register_movement(member, entry(item, farm, note="Compra"))

    assert created is True
    assert (movement.kind, movement.quantity, movement.note, movement.actor_id) == (
        "entry",
        Decimal("300"),
        "Compra",
        member.pk,
    )
    assert stock.quantity == Decimal("300.000")
    assert stock.last_count_date is None
    assert InputStock.objects.count() == 1


def test_entries_add_up(member, item, farm):
    register_movement(member, entry(item, farm, "300"))
    register_movement(member, entry(item, farm, "50.5"))

    assert stock_of(item, farm).quantity == Decimal("350.500")


def test_a_count_leaves_the_stock_at_the_counted_quantity(member, item, farm):
    register_movement(member, entry(item, farm, "250"))

    movement, stock, _ = register_movement(member, count(item, farm, "230"))

    assert (movement.quantity, movement.counted_quantity) == (Decimal("-20"), Decimal("230"))
    assert stock.quantity == Decimal("230.000")
    assert stock.last_count_date == TODAY


@pytest.mark.parametrize("counted, difference", [("300", "50"), ("250", "0"), ("0", "-250")])
def test_a_count_records_a_positive_negative_or_zero_difference(
    member, item, farm, counted, difference
):
    register_movement(member, entry(item, farm, "250"))

    movement, stock, _ = register_movement(member, count(item, farm, counted))

    assert movement.quantity == Decimal(difference)
    assert stock.quantity == Decimal(counted)


def test_a_count_without_previous_stock_counts_from_zero(member, item, farm):
    movement, stock, _ = register_movement(member, count(item, farm, "40"))

    assert (movement.quantity, stock.quantity) == (Decimal("40"), Decimal("40"))


def test_an_older_count_does_not_move_the_last_count_date_back(member, item, farm):
    register_movement(member, count(item, farm, "10", occurred_on=TODAY))

    _, stock, _ = register_movement(
        member, count(item, farm, "20", occurred_on=TODAY - timedelta(days=5))
    )

    assert stock.last_count_date == TODAY


def test_a_consumption_subtracts_and_can_leave_the_stock_negative(member, item, farm):
    register_movement(member, entry(item, farm, "30"))

    movement = item.record_consumption(farm, Decimal("50"), TODAY, "Fertilización · P-03", member)

    assert (movement.kind, movement.quantity, movement.note) == (
        "consumption",
        Decimal("-50"),
        "Fertilización · P-03",
    )
    assert stock_of(item, farm).quantity == Decimal("-20.000")


def test_a_consumption_is_accepted_for_an_inactive_input_and_farm(member, item, farm):
    register_movement(member, entry(item, farm, "30"))
    type(item).objects.filter(pk=item.pk).update(is_active=False)
    Farm.objects.filter(pk=farm.pk).update(is_active=False)

    movement = record_consumption(item, farm, Decimal("10"), TODAY, "", member)

    assert movement.quantity == Decimal("-10")
    assert stock_of(item, farm).quantity == Decimal("20.000")


def test_a_consumption_needs_a_positive_quantity(member, item, farm):
    with pytest.raises(ValueError):
        record_consumption(item, farm, Decimal("0"), TODAY, "", member)


def test_each_farm_has_its_own_stock(member, producer, item, farm):
    other = FarmFactory(producer=producer)

    register_movement(member, entry(item, farm, "100"))

    assert not InputStock.objects.filter(input=item, farm=other).exists()


def test_the_stock_is_always_the_sum_of_its_movements(member, item, farm):
    register_movement(member, entry(item, farm, "300"))
    register_movement(member, count(item, farm, "250"))
    record_consumption(item, farm, Decimal("70"), TODAY, "", member)
    register_movement(member, entry(item, farm, "12.345"))
    register_movement(member, count(item, farm, "0"))

    total = InputMovement.objects.filter(input=item, farm=farm).aggregate(t=Sum("quantity"))["t"]
    assert stock_of(item, farm).quantity == total == Decimal("0.000")


def test_an_inactive_input_does_not_accept_entries_but_does_accept_counts(member, item, farm):
    type(item).objects.filter(pk=item.pk).update(is_active=False)

    with pytest.raises(InputInactive):
        register_movement(member, entry(item, farm))
    assert not InputStock.objects.exists()

    register_movement(member, count(item, farm, "0"))


def test_an_inactive_farm_accepts_nothing(member, item, farm):
    Farm.objects.filter(pk=farm.pk).update(is_active=False)

    with pytest.raises(FarmInactive):
        register_movement(member, entry(item, farm))
    with pytest.raises(FarmInactive):
        register_movement(member, count(item, farm))
    assert not InputMovement.objects.exists()


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"quantity": Decimal("0")}, "quantity"),
        ({"quantity": Decimal("-1")}, "quantity"),
        ({"quantity": None}, "quantity"),
        ({"quantity": Decimal("10000000")}, "quantity"),
        ({"counted_quantity": Decimal("5")}, "counted_quantity"),
        ({"occurred_on": TODAY + timedelta(days=1)}, "occurred_on"),
        ({"note": "x" * 201}, "note"),
        ({"kind": "consumption"}, "kind"),
    ],
)
def test_an_invalid_entry_is_rejected_and_writes_nothing(member, item, farm, changes, field):
    with pytest.raises(ValidationError) as error:
        register_movement(member, entry(item, farm, **changes))

    assert field in error.value.detail
    assert not InputMovement.objects.exists()
    assert not InputStock.objects.exists()


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"counted_quantity": Decimal("-1")}, "counted_quantity"),
        ({"counted_quantity": None}, "counted_quantity"),
        ({"quantity": Decimal("5")}, "quantity"),
    ],
)
def test_an_invalid_count_is_rejected(member, item, farm, changes, field):
    with pytest.raises(ValidationError) as error:
        register_movement(member, count(item, farm, **changes))

    assert field in error.value.detail


def test_an_input_and_a_farm_of_different_producers_are_rejected_for_the_technical_account(
    item,
):
    other_farm = FarmFactory()

    with pytest.raises(ValidationError) as error:
        register_movement(UserFactory(is_superuser=True), entry(item, other_farm))

    assert "farm_id" in error.value.detail


def test_someone_elses_input_or_farm_is_not_found(member, item, farm):
    foreign_input = AgriculturalInputFactory()
    foreign_farm = FarmFactory()

    with pytest.raises(InputNotFound):
        register_movement(member, entry(foreign_input, farm))
    with pytest.raises(FarmNotFound):
        register_movement(member, entry(item, foreign_farm))
    assert not InputMovement.objects.exists()


def test_the_technical_account_registers_for_any_producer(item, farm):
    technical = UserFactory(is_superuser=True)

    movement, _, _ = register_movement(technical, entry(item, farm))

    assert movement.actor_id == technical.pk


def test_resending_the_same_id_and_content_does_not_duplicate(member, item, farm):
    movement_id = uuid.uuid4()
    first, _, created = register_movement(member, entry(item, farm, id=movement_id))

    again, stock, created_again = register_movement(member, entry(item, farm, id=movement_id))

    assert (created, created_again) == (True, False)
    assert again.pk == first.pk
    assert stock.quantity == Decimal("300.000")
    assert InputMovement.objects.count() == 1


def test_resending_a_count_with_the_same_id_does_not_count_again(member, item, farm):
    movement_id = uuid.uuid4()
    register_movement(member, count(item, farm, "100", id=movement_id))
    register_movement(member, entry(item, farm, "5"))

    _, stock, created = register_movement(member, count(item, farm, "100", id=movement_id))

    assert created is False
    assert stock.quantity == Decimal("105.000")


def test_resending_an_id_with_other_content_is_a_conflict(member, item, farm):
    movement_id = uuid.uuid4()
    register_movement(member, entry(item, farm, "300", id=movement_id))

    with pytest.raises(MovementIdConflict):
        register_movement(member, entry(item, farm, "999", id=movement_id))
    assert stock_of(item, farm).quantity == Decimal("300.000")


def test_an_id_that_belongs_to_another_producers_movement_is_a_conflict(member, item, farm):
    foreign_item = AgriculturalInputFactory()
    foreign_farm = FarmFactory(producer=foreign_item.producer)
    movement_id = uuid.uuid4()
    register_movement(
        UserFactory(producer=foreign_item.producer),
        entry(foreign_item, foreign_farm, id=movement_id),
    )

    with pytest.raises(MovementIdConflict):
        register_movement(member, entry(item, farm, id=movement_id))


@pytest.mark.django_db(transaction=True)
def test_simultaneous_entries_and_consumptions_lose_nothing():
    producer = ProducerFactory()
    user = UserFactory(producer=producer)
    item = AgriculturalInputFactory(producer=producer, unit="ml")
    farm = FarmFactory(producer=producer)
    register_movement(user, entry(item, farm, "1000"))

    def act(index):
        if index % 2:
            register_movement(user, entry(item, farm, "10"))
        else:
            record_consumption(item, farm, Decimal("5"), TODAY, "", user)

    run_in_parallel(act, list(range(8)))

    # 4 entradas de +10 y 4 salidas de -5 sobre 1000.
    assert stock_of(item, farm).quantity == Decimal("1020.000")
    assert InputMovement.objects.filter(input=item).count() == 9


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_sends_of_the_same_id_register_it_once():
    producer = ProducerFactory()
    user = UserFactory(producer=producer)
    item = AgriculturalInputFactory(producer=producer, unit="ml")
    farm = FarmFactory(producer=producer)
    data = entry(item, farm, "300", id=uuid.uuid4())

    results = run_in_parallel(lambda _: register_movement(user, dict(data)), [1, 2])

    assert sorted(created for _, _, created in results) == [False, True]
    assert stock_of(item, farm).quantity == Decimal("300.000")
    assert InputMovement.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_a_count_concurrent_with_a_consumption_leaves_the_counted_quantity():
    producer = ProducerFactory()
    user = UserFactory(producer=producer)
    item = AgriculturalInputFactory(producer=producer, unit="ml")
    farm = FarmFactory(producer=producer)
    register_movement(user, entry(item, farm, "100"))

    def act(index):
        if index == 0:
            register_movement(user, count(item, farm, "40"))
        else:
            record_consumption(item, farm, Decimal("10"), TODAY, "", user)

    run_in_parallel(act, [0, 1])

    total = InputMovement.objects.filter(input=item, farm=farm).aggregate(t=Sum("quantity"))["t"]
    assert stock_of(item, farm).quantity == total
    # O el conteo fue último (40) o la salida lo fue (30): nunca se pierde un movimiento.
    assert stock_of(item, farm).quantity in (Decimal("40.000"), Decimal("30.000"))


def test_an_entry_that_would_overflow_the_stock_is_rejected_not_a_500(member, item, farm):
    InputStock.objects.create(input=item, farm=farm, quantity=Decimal("999999999.000"))

    with pytest.raises(ValidationError) as error:
        register_movement(member, entry(item, farm, "1"))

    assert "quantity" in error.value.detail
    assert not InputMovement.objects.exists()
    assert stock_of(item, farm).quantity == Decimal("999999999.000")


def test_a_count_whose_difference_overflows_is_rejected_on_the_counted_field(member, item, farm):
    InputStock.objects.create(input=item, farm=farm, quantity=Decimal("-999999999.000"))

    with pytest.raises(ValidationError) as error:
        register_movement(member, count(item, farm, "9999999"))

    assert "counted_quantity" in error.value.detail


def test_a_consumption_that_would_overflow_the_stock_is_rejected(member, item, farm):
    InputStock.objects.create(input=item, farm=farm, quantity=Decimal("-999999999.000"))

    with pytest.raises(ValidationError):
        record_consumption(item, farm, Decimal("1"), TODAY, "", member)


def test_a_consumption_with_a_farm_of_another_producer_is_a_programming_error(member, item):
    with pytest.raises(ValueError):
        record_consumption(item, FarmFactory(), Decimal("1"), TODAY, "", member)
    assert not InputMovement.objects.exists()
