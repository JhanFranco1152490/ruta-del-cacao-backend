"""Las actividades en la bitácora: el responsable por su nombre y los insumos usados."""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.activities.models import AgriculturalActivityAuditEvent
from apps.activities.services.audit import plan_values, record_activity_event
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.common.contracts.audit_log import audit_source
from apps.common.serializers import full_name
from apps.inputs.tests.factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


def _describe(*events):
    return audit_source("activity").describe([event.pk for event in events])


def test_an_activity_is_named_by_its_type_and_its_plot():
    activity = AgriculturalActivityFactory(activity_type="pruning")
    event = record_activity_event(
        activity=activity, actor=None, action="created", before={}, after=plan_values(activity)
    )

    [entry] = _describe(event)

    assert entry.record_label == f"Poda · {activity.plot.code}"
    changes = {change.field: change for change in entry.changes}
    assert changes["activity_type"].after == "Poda"
    assert changes["assignee_id"].after == full_name(activity.assignee)
    assert changes["scheduled_date"].kind == "date"


def test_the_inputs_used_are_shown_by_their_names():
    activity = AgriculturalActivityFactory()
    urea = AgriculturalInputFactory(name="Urea", producer=activity.plot.farm.producer)
    event = record_activity_event(
        activity=activity,
        actor=None,
        action="completed",
        before={"inputs": None},
        after={"inputs": [{"input_id": str(urea.pk), "quantity": "2.000"}]},
    )

    [change] = _describe(event)[0].changes

    assert (change.label, change.before, change.after) == ("Insumos usados", None, "Urea: 2.000")


def test_a_deleted_activity_is_named_by_what_its_event_kept():
    activity = AgriculturalActivityFactory(activity_type="irrigation")
    event = record_activity_event(
        activity=activity, actor=None, action="deleted", before=plan_values(activity), after={}
    )
    AgriculturalActivityAuditEvent.objects.filter(pk=event.pk).update(activity=None)

    [entry] = _describe(event)

    assert (entry.record_label, entry.record_deleted) == (f"Riego · {activity.plot.code}", True)


def test_many_events_take_the_same_queries(django_assert_max_num_queries):
    activity = AgriculturalActivityFactory()
    events = []
    for _ in range(30):
        assignee = UserFactory(producer=activity.plot.farm.producer)
        events.append(
            record_activity_event(
                activity=activity,
                actor=UserFactory(),
                action="updated",
                before={"assignee_id": activity.assignee_id},
                after={"assignee_id": assignee.pk},
            )
        )

    # Los eventos con su actividad, las parcelas, los responsables y los insumos: a lo sumo
    # cuatro (sin insumos usados, esa no se pide).
    with django_assert_max_num_queries(4):
        entries = _describe(*events)

    assert len(entries) == 30
