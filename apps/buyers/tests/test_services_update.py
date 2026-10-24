import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.buyers.exceptions import BuyerNotFound, DuplicateBuyerDocument, StaleBuyerVersion
from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.buyers.services import update_buyer
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


@pytest.fixture
def buyer(producer):
    return BuyerFactory(producer=producer, name="Cacao Andino", identity_document="900123456")


def events(action) -> list[BuyerAuditEvent]:
    return list(BuyerAuditEvent.objects.filter(action=action))


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Cacao Andino S.A.S."},
        {"document_type": "CC", "identity_document": "1090123456"},
        {"buyer_type": "exporter"},
        {"contact_name": "Persona Dos"},
        {"phone": "3109876543"},
        {"email": "ventas@example.com"},
    ],
)
def test_every_field_can_be_changed_and_leaves_its_event(member, buyer, changes):
    updated = update_buyer(member, buyer.pk, 1, changes)

    assert updated.version == 2
    for name, value in changes.items():
        assert getattr(updated, name) == value
    (event,) = events("updated")
    assert sorted(event.changed_fields) == sorted(changes)
    assert event.version == 2


def test_the_document_cannot_take_one_another_buyer_has(member, producer, buyer):
    other = BuyerFactory(producer=producer, identity_document="800111222")

    with pytest.raises(DuplicateBuyerDocument) as error:
        update_buyer(member, buyer.pk, 1, {"identity_document": "800111222"})

    assert error.value.extra["existing"]["id"] == str(other.pk)
    buyer.refresh_from_db()
    assert (buyer.identity_document, buyer.version) == ("900123456", 1)


def test_removing_the_only_contact_is_rejected(member, buyer):
    with pytest.raises(ValidationError) as error:
        update_buyer(member, buyer.pk, 1, {"phone": None})

    assert set(error.value.message_dict) == {"phone", "email"}
    buyer.refresh_from_db()
    assert buyer.phone == "3001234567"


def test_the_phone_can_go_when_there_is_an_email(member, buyer):
    updated = update_buyer(member, buyer.pk, 1, {"phone": None, "email": "compras@example.com"})

    assert (updated.phone, updated.email) == (None, "compras@example.com")


def test_deactivating_and_activating_leave_a_status_event(member, buyer):
    inactive = update_buyer(member, buyer.pk, 1, {"is_active": False})
    active = update_buyer(member, buyer.pk, 2, {"is_active": True})

    assert inactive.version == 2
    assert active.is_active is True
    assert [event.changed_fields for event in events("status_changed")] == [
        ["is_active"],
        ["is_active"],
    ]
    assert not events("updated")


def test_an_inactive_buyer_can_be_edited(member, producer):
    inactive = BuyerFactory(producer=producer, is_active=False)

    updated = update_buyer(member, inactive.pk, 1, {"name": "Nuevo nombre"})

    assert (updated.name, updated.is_active) == ("Nuevo nombre", False)


def test_without_real_changes_the_version_does_not_go_up(member, buyer):
    same = update_buyer(member, buyer.pk, 1, {"name": "  Cacao Andino ", "phone": "3001234567"})

    assert same.version == 1
    assert not BuyerAuditEvent.objects.exists()


def test_a_stale_version_returns_the_current_buyer(member, buyer):
    update_buyer(member, buyer.pk, 1, {"name": "Cacao Andino 2"})

    with pytest.raises(StaleBuyerVersion) as error:
        update_buyer(member, buyer.pk, 1, {"name": "Otro"})

    assert error.value.current_buyer.name == "Cacao Andino 2"
    assert error.value.current_buyer.has_records is False


def test_retrying_an_applied_change_with_an_old_version_is_a_no_op(member, buyer):
    update_buyer(member, buyer.pk, 1, {"name": "Cacao Andino 2"})

    again = update_buyer(member, buyer.pk, 1, {"name": "Cacao Andino 2"})

    assert again.version == 2
    assert len(events("updated")) == 1


def test_another_producers_buyer_is_not_found(member):
    foreign = BuyerFactory()

    with pytest.raises(BuyerNotFound):
        update_buyer(member, foreign.pk, 1, {"name": "Xx"})


def test_a_record_that_points_to_the_buyer_keeps_pointing_after_an_edit(
    member, buyer, buyer_usage_table
):
    sale = buyer_usage_table(buyer)

    updated = update_buyer(
        member, buyer.pk, 1, {"name": "Otro nombre", "identity_document": "700000001"}
    )

    sale.refresh_from_db()
    assert sale.buyer_id == buyer.pk
    assert updated.has_records is True
    assert Buyer.objects.get(pk=buyer.pk).name == "Otro nombre"
