import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.exceptions import ActivityAlreadyDone, InputInactive, InvalidActivity
from apps.activities.models import (
    AgriculturalActivity,
    AgriculturalActivityAuditEvent,
    AgriculturalActivityInput,
)
from apps.activities.services.complete import complete_activity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.inputs.models import AgriculturalInput, InputMovement, InputStock
from apps.inputs.tests.factories import AgriculturalInputFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def plot():
    return PlotFactory(code="P-03")


@pytest.fixture
def activity(plot):
    activity = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.FERTILIZATION, scheduled_date=today_in_bogota()
    )
    AgriculturalActivity.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    activity.refresh_from_db()
    return activity


@pytest.fixture
def actor(plot):
    return UserFactory(producer=plot.farm.producer)


def input_of(plot, **kwargs):
    return AgriculturalInputFactory(producer=plot.farm.producer, **kwargs)


def completion(*inputs, done_date=None):
    return {
        "done_date": done_date or today_in_bogota(),
        "inputs": [{"input_id": item.pk, "quantity": quantity} for item, quantity in inputs],
        "captured_at": None,
    }


def stock_of(item, farm):
    return InputStock.objects.get(input=item, farm=farm).quantity


def test_it_records_each_input_and_discounts_it_from_the_farm(actor, activity, plot):
    urea = input_of(plot, name="Urea 46 %")
    lime = input_of(plot, name="Cal dolomita")

    _, changed = complete_activity(
        actor, activity.pk, completion((urea, Decimal("100")), (lime, Decimal("2.5")))
    )

    assert changed is True
    used = {
        row.input_id: row for row in AgriculturalActivityInput.objects.filter(activity=activity)
    }
    assert used[urea.pk].quantity == Decimal("100.000")
    assert used[lime.pk].quantity == Decimal("2.500")
    movement = used[urea.pk].stock_movement
    assert movement.kind == InputMovement.Kind.CONSUMPTION
    assert movement.quantity == Decimal("-100.000")
    assert movement.farm_id == plot.farm_id
    assert movement.occurred_on == today_in_bogota()
    assert movement.actor == actor
    assert stock_of(urea, plot.farm) == Decimal("-100.000")
    assert stock_of(lime, plot.farm) == Decimal("-2.500")


def test_the_movement_says_which_task_it_came_from(actor, activity, plot):
    urea = input_of(plot)

    complete_activity(actor, activity.pk, completion((urea, Decimal("1"))))

    assert InputMovement.objects.get(input=urea).note == "Fertilización · P-03"


def test_other_uses_its_description_in_the_note(actor, plot):
    other = AgriculturalActivityFactory(
        plot=plot,
        activity_type=ActivityType.OTHER,
        other_description="Resiembra",
        scheduled_date=today_in_bogota(),
    )
    seedlings = input_of(plot, unit=AgriculturalInput.Unit.UNIT)

    complete_activity(actor, other.pk, completion((seedlings, Decimal("40"))))

    assert InputMovement.objects.get(input=seedlings).note == "Resiembra · P-03"


def test_the_stock_may_end_negative(actor, activity, plot):
    urea = input_of(plot)

    complete_activity(actor, activity.pk, completion((urea, Decimal("500"))))

    assert stock_of(urea, plot.farm) == Decimal("-500.000")


def test_the_completed_event_lists_the_inputs(actor, activity, plot):
    urea = input_of(plot)

    complete_activity(actor, activity.pk, completion((urea, Decimal("2"))))

    event = AgriculturalActivityAuditEvent.objects.get(
        activity=activity, action=AgriculturalActivityAuditEvent.Action.COMPLETED
    )
    assert event.changes["inputs"] == {
        "before": None,
        "after": [{"input_id": str(urea.pk), "quantity": "2.000"}],
    }


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1")])
def test_the_quantity_must_be_greater_than_zero(actor, activity, plot, quantity):
    with pytest.raises(InvalidActivity) as error:
        complete_activity(actor, activity.pk, completion((input_of(plot), quantity)))

    assert "inputs" in error.value.fields


def test_an_input_is_not_repeated(actor, activity, plot):
    urea = input_of(plot)

    with pytest.raises(InvalidActivity) as error:
        complete_activity(
            actor, activity.pk, completion((urea, Decimal("1")), (urea, Decimal("2")))
        )

    assert error.value.fields["inputs"] == ["Este insumo ya está en la lista."]


@pytest.mark.parametrize("whose", ["another-producer", "missing"])
def test_an_input_outside_the_catalog_is_a_validation_error_not_a_404(
    actor, activity, plot, whose
):
    # Un 404 lo leería la cola como una actividad eliminada y descartaría el registro.
    item = AgriculturalInputFactory() if whose == "another-producer" else None
    sent = completion()
    sent["inputs"] = [{"input_id": item.pk if item else uuid.uuid4(), "quantity": Decimal("1")}]

    with pytest.raises(InvalidActivity) as error:
        complete_activity(actor, activity.pk, sent)

    assert "inputs" in error.value.fields


def test_an_inactive_input_is_rejected_with_its_id(actor, activity, plot):
    active = input_of(plot)
    inactive = input_of(plot, is_active=False)

    with pytest.raises(InputInactive) as error:
        complete_activity(
            actor, activity.pk, completion((active, Decimal("1")), (inactive, Decimal("1")))
        )

    assert error.value.extra["input_ids"] == [str(inactive.pk)]
    assert not InputMovement.objects.exists()


def test_an_inventory_task_takes_no_inputs(actor, plot):
    inventory = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.INVENTORY, scheduled_date=today_in_bogota()
    )

    with pytest.raises(InvalidActivity) as error:
        complete_activity(actor, inventory.pk, completion((input_of(plot), Decimal("1"))))

    assert "inputs" in error.value.fields


def test_a_resend_does_not_discount_twice(actor, activity, plot):
    urea = input_of(plot)
    complete_activity(actor, activity.pk, completion((urea, Decimal("2"))))

    again, changed = complete_activity(actor, activity.pk, completion((urea, Decimal("2.000"))))

    assert changed is False
    assert again.version == 2
    assert InputMovement.objects.filter(input=urea).count() == 1
    assert stock_of(urea, plot.farm) == Decimal("-2.000")


def test_a_resend_with_other_inputs_is_already_done(actor, activity, plot):
    urea = input_of(plot)
    complete_activity(actor, activity.pk, completion((urea, Decimal("2"))))

    with pytest.raises(ActivityAlreadyDone):
        complete_activity(actor, activity.pk, completion((urea, Decimal("3"))))

    assert stock_of(urea, plot.farm) == Decimal("-2.000")


def test_a_failure_while_discounting_reverts_the_completion(actor, activity, plot, monkeypatch):
    urea = input_of(plot)

    def broken(self, *args, **kwargs):
        raise RuntimeError("inventory down")

    monkeypatch.setattr(AgriculturalInput, "record_consumption", broken)

    with pytest.raises(RuntimeError):
        complete_activity(actor, activity.pk, completion((urea, Decimal("2"))))

    activity.refresh_from_db()
    assert activity.status == ActivityStatus.SCHEDULED
    assert not AgriculturalActivityInput.objects.exists()
