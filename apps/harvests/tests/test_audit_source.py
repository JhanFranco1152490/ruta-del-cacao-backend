"""Las cosechas en la bitácora: su fecha y su parcela, y el recolector por su nombre."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.contracts.audit_log import audit_source
from apps.common.serializers import full_name
from apps.harvests.models import HarvestAuditEvent
from apps.harvests.services.audit import harvest_values, record_harvest_event
from apps.harvests.tests.factories import HarvestFactory

pytestmark = pytest.mark.django_db


def _describe(*events):
    return audit_source("harvest").describe([event.pk for event in events])


def _corrected(harvest, collector):
    before = harvest_values(harvest)
    harvest.collector = collector
    harvest.green_weight_kg = Decimal("125.0")
    return record_harvest_event(
        harvest=harvest,
        actor=UserFactory(),
        action="updated",
        before=before,
        after=harvest_values(harvest),
    )


def test_a_correction_shows_the_collector_by_name_and_the_weight_as_a_number():
    harvest = HarvestFactory(harvest_date=date(2026, 11, 14), green_weight_kg=Decimal("120.5"))
    previous = harvest.collector
    collector = UserFactory(
        producer=harvest.plot.farm.producer, first_name="Ana", last_name="Ruiz"
    )
    event = _corrected(harvest, collector)

    [entry] = _describe(event)

    assert entry.record_label == f"Cosecha del 14/11/2026 · {harvest.plot.code}"
    assert entry.action_label == "Cosecha corregida"
    changes = {change.field: change for change in entry.changes}
    assert (changes["green_weight_kg"].before, changes["green_weight_kg"].after) == (
        "120.5",
        "125.0",
    )
    assert changes["green_weight_kg"].kind == "number"
    assert (changes["collector_id"].label, changes["collector_id"].after) == (
        "Recolector",
        "Ana Ruiz",
    )
    assert changes["collector_id"].before == full_name(previous)


def test_a_deleted_harvest_is_named_by_the_date_its_event_kept():
    harvest = HarvestFactory(harvest_date=date(2026, 11, 14))
    event = record_harvest_event(
        harvest=harvest,
        actor=None,
        action="deleted",
        before=harvest_values(harvest),
        after={},
    )
    HarvestAuditEvent.objects.filter(pk=event.pk).update(harvest=None)

    [entry] = _describe(event)

    assert entry.record_label.startswith("Cosecha del 14/11/2026")
    assert entry.record_deleted


def test_many_corrections_take_the_same_queries(django_assert_max_num_queries):
    harvest = HarvestFactory()
    events = [
        _corrected(harvest, UserFactory(producer=harvest.plot.farm.producer)) for _ in range(30)
    ]

    # Los eventos con su cosecha, las parcelas, las variedades y los recolectores: a lo sumo
    # cuatro (sin una variedad que traducir, esa no se pide).
    with django_assert_max_num_queries(4):
        entries = _describe(*events)

    assert len(entries) == 30
