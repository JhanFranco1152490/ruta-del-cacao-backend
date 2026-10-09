from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.inputs.exceptions import (
    DuplicateInput,
    InputNotFound,
    InputUnitLocked,
    StaleInputVersion,
)
from apps.inputs.models import AgriculturalInputAuditEvent
from apps.inputs.services import update_input
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


@pytest.fixture
def item(producer):
    return AgriculturalInputFactory(
        producer=producer, name="Urea", name_normalized="urea", unit="kg"
    )


def events(item):
    return AgriculturalInputAuditEvent.objects.filter(input_ref=item.pk).order_by("occurred_at")


def test_changes_name_and_type_bumps_the_version_and_records_before_and_after(member, item):
    updated = update_input(member, item.pk, 1, {"name": "Urea 46 %", "input_type": "other"})

    assert (updated.name, updated.input_type, updated.version) == ("Urea 46 %", "other", 2)
    item.refresh_from_db()
    assert item.name_normalized == "urea46%"
    event = events(item).get()
    assert (event.action, event.version, event.actor_id) == ("updated", 2, member.pk)
    assert event.changes == {
        "name": {"before": "Urea", "after": "Urea 46 %"},
        "input_type": {"before": "fertilizer", "after": "other"},
    }


def test_deactivating_only_leaves_a_status_changed_event(member, item):
    updated = update_input(member, item.pk, 1, {"is_active": False})

    assert updated.is_active is False
    event = events(item).get()
    assert event.action == "status_changed"
    assert event.changes == {"is_active": {"before": True, "after": False}}


def test_changing_content_and_status_leaves_two_events(member, item):
    update_input(member, item.pk, 1, {"name": "Urea 46", "is_active": False})

    assert [event.action for event in events(item)] == ["updated", "status_changed"]


@pytest.mark.parametrize("data", [{"name": "  Urea "}, {"name": "Urea", "unit": "kg"}])
def test_without_real_changes_nothing_is_written(member, item, data):
    updated = update_input(member, item.pk, 1, data)

    assert updated.version == 1
    item.refresh_from_db()
    assert item.version == 1
    assert events(item).count() == 0


def test_a_stale_version_returns_the_current_input(member, item):
    update_input(member, item.pk, 1, {"name": "Urea 2"})

    with pytest.raises(StaleInputVersion) as error:
        update_input(member, item.pk, 1, {"name": "Otro"})

    assert error.value.current_input.name == "Urea 2"
    assert error.value.current_input.has_records is False
    item.refresh_from_db()
    assert item.name == "Urea 2"


def test_retrying_an_applied_change_with_an_old_version_is_a_no_op(member, item):
    update_input(member, item.pk, 1, {"name": "Urea 2"})

    again = update_input(member, item.pk, 1, {"name": "Urea 2"})

    assert again.version == 2
    assert events(item).count() == 1


def test_a_name_of_another_input_of_the_same_type_is_a_duplicate(member, producer, item):
    other = AgriculturalInputFactory(
        producer=producer, name="Triple 15", name_normalized="triple15"
    )

    with pytest.raises(DuplicateInput) as error:
        update_input(member, item.pk, 1, {"name": "TRIPLE-15"})

    assert error.value.extra["existing"]["id"] == str(other.pk)
    item.refresh_from_db()
    assert (item.name, item.version) == ("Urea", 1)
    assert events(item).count() == 0


def test_the_package_can_be_added_changed_and_removed(member, item):
    added = update_input(
        member, item.pk, 1, {"package_type": "sack", "package_size": Decimal("50")}
    )
    assert (added.package_type, added.package_size) == ("sack", Decimal("50.000"))
    assert events(item).get().changes["package_size"] == {"before": None, "after": "50.000"}

    changed = update_input(member, item.pk, 2, {"package_size": Decimal("46")})
    assert changed.package_size == Decimal("46.000")

    removed = update_input(member, item.pk, 3, {"package_type": None, "package_size": None})
    assert (removed.package_type, removed.package_size) == (None, None)


def test_removing_only_half_of_the_package_is_rejected(member, producer):
    packed = AgriculturalInputFactory(
        producer=producer, package_type="tub", package_size=Decimal("100"), unit="ml"
    )

    with pytest.raises(Exception) as error:
        update_input(member, packed.pk, 1, {"package_type": None})

    assert "package_type" in error.value.message_dict


def test_the_unit_is_locked_once_the_input_is_used(member, used_input):
    used_input.producer = member.producer
    used_input.save()

    with pytest.raises(InputUnitLocked) as error:
        update_input(member, used_input.pk, 1, {"unit": "l"})

    assert "unit" in error.value.fields
    used_input.refresh_from_db()
    assert used_input.unit == "kg"


def test_the_package_can_change_even_when_the_input_is_used(member, producer, input_usage_table):
    used = AgriculturalInputFactory(
        producer=producer, unit="ml", package_type="tub", package_size=Decimal("100")
    )
    input_usage_table(used)

    updated = update_input(member, used.pk, 1, {"package_type": "bottle", "package_size": "250"})

    assert (updated.package_type, updated.package_size) == ("bottle", Decimal("250.000"))


def test_name_type_and_status_can_change_on_a_used_input(member, producer, input_usage_table):
    used = AgriculturalInputFactory(producer=producer)
    input_usage_table(used)

    updated = update_input(member, used.pk, 1, {"name": "Nuevo", "is_active": False})

    assert (updated.name, updated.is_active, updated.has_records) == ("Nuevo", False, True)


def test_an_inactive_input_can_be_edited(member, producer):
    inactive = AgriculturalInputFactory(producer=producer, is_active=False)

    assert update_input(member, inactive.pk, 1, {"name": "Corregido"}).name == "Corregido"


def test_an_input_of_another_producer_is_not_found(member):
    foreign = AgriculturalInputFactory()

    with pytest.raises(InputNotFound):
        update_input(member, foreign.pk, 1, {"name": "X1"})


def test_the_technical_account_edits_any_input_and_is_the_actor(item):
    technical = UserFactory(is_superuser=True)

    update_input(technical, item.pk, 1, {"name": "Urea 2"})

    assert events(item).get().actor_id == technical.pk
