"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.farms.models import FarmAuditEvent
from apps.farms.services.audit import record_farm_audit_event
from apps.farms.tests.factories import FarmFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.farms.migrations.0011_fill_audit_producer_ref"


def _event():
    farm = FarmFactory()
    event = record_farm_audit_event(farm=farm, actor=UserFactory(), action="updated")
    return event, farm.producer_id


def _orphan():
    farm = FarmFactory()
    event = record_farm_audit_event(farm=farm, actor=UserFactory(), action="deleted")
    FarmAuditEvent.objects.filter(pk=event.pk).update(farm=None)
    farm.delete()
    return event


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    FarmAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(
    _orphan is None, reason="La ficha se elimina con su parcela: no queda huérfana."
)
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan() if _orphan else None
    FarmAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None


def test_audit_events_keeps_the_events_of_the_producer_in_the_local_period_by_the_author():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from apps.common.contracts.audit_log import audit_events

    bogota = ZoneInfo("America/Bogota")
    farm = FarmFactory()
    author, other_author = UserFactory(), UserFactory()
    inside = record_farm_audit_event(farm=farm, actor=author, action="updated")
    # Las 23:30 del 14 en Bogotá son el 15 en UTC: cuentan en el 14.
    FarmAuditEvent.objects.filter(pk=inside.pk).update(
        occurred_at=datetime(2026, 11, 14, 23, 30, tzinfo=bogota)
    )
    late = record_farm_audit_event(farm=farm, actor=author, action="updated")
    FarmAuditEvent.objects.filter(pk=late.pk).update(
        occurred_at=datetime(2026, 11, 15, 0, 30, tzinfo=bogota)
    )
    record_farm_audit_event(farm=farm, actor=other_author, action="updated")
    record_farm_audit_event(farm=FarmFactory(), actor=author, action="updated")

    rows = audit_events(
        FarmAuditEvent.objects.all(),
        farm.producer_id,
        date_from=date(2026, 11, 14),
        date_to=date(2026, 11, 14),
        actor_id=author.pk,
    )

    assert list(rows) == [
        {"id": inside.pk, "occurred_at": rows[0]["occurred_at"], "actor_id": author.pk}
    ]
    assert rows[0]["occurred_at"] == datetime(2026, 11, 14, 23, 30, tzinfo=bogota)
