"""La migración que numera las fincas que ya existían, probada con datos del estado anterior."""

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.common.choices import DocumentType

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [
    ("farms", "0005_farm_deletion_and_surviving_audit"),
    ("producers", "0009_producer_audit_event"),
]
SEQUENCE_MIGRATION = [("producers", "0010_producer_farm_sequence")]


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_state():
    old_apps = migrate(BEFORE)
    yield old_apps
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def make_producer(apps, n):
    return apps.get_model("producers", "Producer").objects.create(
        member_code=f"PROD-{800_000 + n:06d}",
        document_type=DocumentType.CC,
        identity_document=str(30_000_000 + n),
        first_name="Ana",
        last_name=f"Prueba{n}",
        municipality_code="54001",
        joined_on=timezone.localdate(),
    )


def make_farm(apps, producer, name, age_days):
    farm = apps.get_model("farms", "Farm").objects.create(
        producer_id=producer.pk,
        name=name,
        name_normalized=name.lower(),
        department_code="54",
        municipality_code="54001",
        area_hectares=1,
        altitude_masl=900,
        latitude="7.8",
        longitude="-72.5",
    )
    # `created_at` es automática: se fija después para controlar el orden.
    apps.get_model("farms", "Farm").objects.filter(pk=farm.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    return farm


def numbers(apps, producer):
    farms = apps.get_model("farms", "Farm").objects.filter(producer_id=producer.pk)
    return {farm.name: farm.number for farm in farms}


def test_existing_farms_are_numbered_by_creation_date_within_each_producer(old_state):
    first, second = make_producer(old_state, 1), make_producer(old_state, 2)
    make_farm(old_state, first, "Vieja", age_days=10)
    make_farm(old_state, first, "Nueva", age_days=1)
    make_farm(old_state, second, "Unica", age_days=5)

    new_apps = migrate(SEQUENCE_MIGRATION + [("farms", "0008_farm_number_required")])

    assert numbers(new_apps, first) == {"Vieja": 1, "Nueva": 2}
    assert numbers(new_apps, second) == {"Unica": 1}


def test_the_counter_of_each_producer_ends_at_its_last_number(old_state):
    producer = make_producer(old_state, 1)
    make_farm(old_state, producer, "Uno", age_days=3)
    make_farm(old_state, producer, "Dos", age_days=2)

    new_apps = migrate(SEQUENCE_MIGRATION + [("farms", "0008_farm_number_required")])

    stored = new_apps.get_model("producers", "Producer").objects.get(pk=producer.pk)
    assert stored.farm_sequence == 2


def test_farms_created_at_the_same_instant_are_numbered_by_id_without_repeats(old_state):
    producer = make_producer(old_state, 1)
    for name in ("A", "B", "C"):
        farm = make_farm(old_state, producer, name, age_days=0)
        old_state.get_model("farms", "Farm").objects.filter(pk=farm.pk).update(
            created_at=timezone.make_aware(timezone.datetime(2026, 1, 1))
        )

    new_apps = migrate(SEQUENCE_MIGRATION + [("farms", "0008_farm_number_required")])

    assert sorted(numbers(new_apps, producer).values()) == [1, 2, 3]


def test_the_migration_can_be_undone(old_state):
    producer = make_producer(old_state, 1)
    make_farm(old_state, producer, "Uno", age_days=1)
    migrate(SEQUENCE_MIGRATION + [("farms", "0008_farm_number_required")])

    back = migrate(BEFORE)

    assert back.get_model("farms", "Farm").objects.count() == 1
