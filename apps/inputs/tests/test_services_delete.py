import pytest

from apps.accounts.tests.factories import UserFactory
from apps.inputs.exceptions import InputHasRecords, InputNotFound, StaleInputVersion
from apps.inputs.models import AgriculturalInput, AgriculturalInputAuditEvent
from apps.inputs.services import create_input, delete_input, update_input
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory, input_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def member():
    return UserFactory(producer=ProducerFactory())


def test_deletes_an_unused_input_and_keeps_its_history(member):
    item = create_input(member, input_data(name="Urea"))
    update_input(member, item.pk, 1, {"name": "Urea 2"})

    delete_input(member, item.pk, 2)

    assert not AgriculturalInput.objects.exists()
    history = AgriculturalInputAuditEvent.objects.filter(input_ref=item.pk)
    assert [event.action for event in history.order_by("occurred_at")] == [
        "created",
        "updated",
        "deleted",
    ]
    deleted = history.get(action="deleted")
    assert (deleted.input_id, deleted.input_name, deleted.actor_id) == (None, "Urea 2", member.pk)


def test_a_stale_version_does_not_delete(member):
    item = create_input(member, input_data())
    update_input(member, item.pk, 1, {"name": "Otro nombre"})

    with pytest.raises(StaleInputVersion) as error:
        delete_input(member, item.pk, 1)

    assert error.value.current_input.version == 2
    assert AgriculturalInput.objects.count() == 1


def test_an_input_with_records_is_not_deleted_and_leaves_no_event(member, input_usage_table):
    item = AgriculturalInputFactory(producer=member.producer)
    input_usage_table(item)

    with pytest.raises(InputHasRecords):
        delete_input(member, item.pk, 1)

    assert AgriculturalInput.objects.count() == 1
    assert not AgriculturalInputAuditEvent.objects.filter(action="deleted").exists()


def test_an_input_of_another_producer_is_not_found(member):
    foreign = AgriculturalInputFactory()

    with pytest.raises(InputNotFound):
        delete_input(member, foreign.pk, 1)
    assert AgriculturalInput.objects.count() == 1
