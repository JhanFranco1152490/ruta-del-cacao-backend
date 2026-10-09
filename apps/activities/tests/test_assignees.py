import pytest

from apps.accounts.tests.factories import UserFactory
from apps.activities.exceptions import InvalidActivity
from apps.activities.services.queries import assignee_options
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


def names(options):
    return [option["full_name"] for option in options]


def test_it_lists_the_accounts_of_the_producer_by_surname(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Zapata")
    UserFactory(producer=producer, first_name="Luis", last_name="Gómez")
    UserFactory(producer=ProducerFactory(), first_name="Otro", last_name="Productor")

    assert names(assignee_options(actor)) == ["Luis Gómez", "Ana Zapata"]


def test_inactive_accounts_are_listed_and_marked(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Activa")
    UserFactory(producer=producer, first_name="Ina", last_name="Inactiva", is_active=False)

    options = {option["full_name"]: option["is_active"] for option in assignee_options(actor)}

    assert options == {"Ana Activa": True, "Ina Inactiva": False}


def test_only_the_id_the_name_and_the_status_are_given(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Zapata")

    [option] = assignee_options(actor)

    assert set(option) == {"id", "full_name", "is_active"}
    assert option["id"] == actor.pk


def test_an_account_without_a_name_is_shown_by_its_email(producer):
    actor = UserFactory(producer=producer, first_name="", last_name="", email="sin@example.com")

    assert names(assignee_options(actor)) == ["sin@example.com"]


def test_a_producer_sent_by_another_account_is_ignored(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Zapata")
    UserFactory(producer=ProducerFactory(), first_name="Otro", last_name="Productor")

    assert names(assignee_options(actor, producer_id=ProducerFactory().pk)) == ["Ana Zapata"]


def test_the_technical_account_chooses_the_producer(producer):
    UserFactory(producer=producer, first_name="Ana", last_name="Zapata")
    superuser = UserFactory(is_superuser=True)

    assert names(assignee_options(superuser, producer_id=producer.pk)) == ["Ana Zapata"]


def test_the_technical_account_must_say_which_producer():
    with pytest.raises(InvalidActivity) as error:
        assignee_options(UserFactory(is_superuser=True))

    assert "producer" in error.value.fields


def test_an_account_without_a_producer_gets_nobody():
    UserFactory(producer=ProducerFactory())

    assert assignee_options(UserFactory()) == []
