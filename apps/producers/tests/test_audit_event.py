import pytest

from apps.accounts.tests.factories import UserFactory
from apps.producers.models import ProducerAuditEvent

pytestmark = pytest.mark.django_db


def _event(actor=None, **overrides):
    return ProducerAuditEvent.objects.create(
        member_code="PROD-000007",
        producer_name="Ana Ejemplo",
        actor=actor,
        action=ProducerAuditEvent.Action.DELETED,
        **overrides,
    )


def test_an_event_needs_no_producer_to_exist():
    # No tiene relación con `Producer`: es lo que queda cuando el productor ya no está.
    event = _event(farms_deleted=2, accounts_deleted=1)

    event.refresh_from_db()
    assert (event.member_code, event.producer_name) == ("PROD-000007", "Ana Ejemplo")
    assert (event.farms_deleted, event.accounts_deleted) == (2, 1)


def test_the_event_survives_the_account_of_whoever_acted():
    actor = UserFactory()
    event = _event(actor=actor)

    actor.delete()

    event.refresh_from_db()
    assert event.actor is None


def test_events_list_the_most_recent_first():
    first = _event()
    second = _event()

    assert list(ProducerAuditEvent.objects.all()) == [second, first]


def test_it_only_keeps_counts_and_never_personal_data_of_the_deleted_accounts():
    names = {field.name for field in ProducerAuditEvent._meta.get_fields()}

    assert names == {
        "id",
        "member_code",
        "producer_name",
        "actor",
        "action",
        "farms_deleted",
        "accounts_deleted",
        "occurred_at",
    }
