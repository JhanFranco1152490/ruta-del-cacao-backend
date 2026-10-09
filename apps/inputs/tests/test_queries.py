import pytest

from apps.accounts.tests.factories import UserFactory
from apps.inputs.exceptions import InputNotFound
from apps.inputs.services import get_input, list_inputs
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


def test_the_catalog_is_ordered_by_name_and_includes_inactive_inputs(producer, member):
    AgriculturalInputFactory(producer=producer, name="Zinc", name_normalized="zinc")
    AgriculturalInputFactory(
        producer=producer, name="Abono", name_normalized="abono", is_active=False
    )

    names = [item.name for item in list_inputs(member)]

    assert names == ["Abono", "Zinc"]


def test_a_producer_only_sees_its_own_inputs(producer, member):
    own = AgriculturalInputFactory(producer=producer)
    AgriculturalInputFactory()

    assert list(list_inputs(member)) == [own]


def test_an_account_without_a_producer_sees_nothing():
    AgriculturalInputFactory()

    assert list(list_inputs(UserFactory())) == []


def test_the_technical_account_sees_every_input_and_can_filter_by_producer(producer):
    first = AgriculturalInputFactory(producer=producer)
    second = AgriculturalInputFactory()
    technical = UserFactory(is_superuser=True)

    assert set(list_inputs(technical)) == {first, second}
    assert list(list_inputs(technical, producer=producer.pk)) == [first]


def test_other_accounts_cannot_choose_the_producer(producer, member):
    own = AgriculturalInputFactory(producer=producer)
    AgriculturalInputFactory()

    assert list(list_inputs(member, producer=ProducerFactory().pk)) == [own]


def test_getting_an_input_of_another_producer_is_not_found(member):
    foreign = AgriculturalInputFactory()

    with pytest.raises(InputNotFound):
        get_input(member, foreign.pk)


def test_the_list_costs_a_constant_number_of_queries(
    producer, member, django_assert_max_num_queries
):
    for _ in range(20):
        AgriculturalInputFactory(producer=producer)

    with django_assert_max_num_queries(2):
        rows = list(list_inputs(member))
        assert [item.producer.member_code for item in rows]


def test_has_records_is_false_without_usage_and_true_with_it(producer, member, input_usage_table):
    unused = AgriculturalInputFactory(producer=producer, name="Libre", name_normalized="libre")
    used = AgriculturalInputFactory(producer=producer, name="Usado", name_normalized="usado")
    input_usage_table(used)

    flags = {item.pk: item.has_records for item in list_inputs(member)}

    assert flags == {unused.pk: False, used.pk: True}
