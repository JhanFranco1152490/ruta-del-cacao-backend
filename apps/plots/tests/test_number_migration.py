"""La migración que numera las parcelas que ya existían, probada con datos del estado anterior."""

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.common.choices import DocumentType

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [
    ("plots", "0002_plot_deletion_and_surviving_audit"),
    ("farms", "0008_farm_number_required"),
]
AFTER = [("plots", "0005_plot_number_required")]


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


def make_farm(apps, n):
    producer = apps.get_model("producers", "Producer").objects.create(
        member_code=f"PROD-{700_000 + n:06d}",
        document_type=DocumentType.CC,
        identity_document=str(40_000_000 + n),
        first_name="Ana",
        last_name=f"Prueba{n}",
        municipality_code="54001",
        joined_on=timezone.localdate(),
        farm_sequence=1,
    )
    return apps.get_model("farms", "Farm").objects.create(
        producer_id=producer.pk,
        number=1,
        name=f"Finca {n}",
        name_normalized=f"finca {n}",
        department_code="54",
        municipality_code="54001",
        area_hectares=50,
        altitude_masl=900,
        latitude="7.8",
        longitude="-72.5",
    )


def make_plot(apps, farm, code, age_days):
    Plot = apps.get_model("plots", "Plot")
    plot = Plot.objects.create(
        farm_id=farm.pk, code=code, code_normalized=code.lower(), area_hectares=1
    )
    Plot.objects.filter(pk=plot.pk).update(created_at=timezone.now() - timedelta(days=age_days))
    return plot


def numbers(apps, farm):
    plots = apps.get_model("plots", "Plot").objects.filter(farm_id=farm.pk)
    return {plot.code: plot.number for plot in plots}


def test_existing_plots_are_numbered_by_creation_date_within_each_farm(old_state):
    first, second = make_farm(old_state, 1), make_farm(old_state, 2)
    make_plot(old_state, first, "La loma", age_days=10)
    make_plot(old_state, first, "P-03", age_days=1)
    make_plot(old_state, second, "Unica", age_days=5)

    new_apps = migrate(AFTER)

    assert numbers(new_apps, first) == {"La loma": 1, "P-03": 2}
    assert numbers(new_apps, second) == {"Unica": 1}


def test_the_counter_of_each_farm_ends_at_its_last_number(old_state):
    farm = make_farm(old_state, 1)
    make_plot(old_state, farm, "Uno", age_days=3)
    make_plot(old_state, farm, "Dos", age_days=2)

    new_apps = migrate(AFTER)

    assert new_apps.get_model("farms", "Farm").objects.get(pk=farm.pk).plot_sequence == 2


def test_plots_created_at_the_same_instant_get_different_numbers(old_state):
    farm = make_farm(old_state, 1)
    for code in ("A", "B", "C"):
        plot = make_plot(old_state, farm, code, age_days=0)
        old_state.get_model("plots", "Plot").objects.filter(pk=plot.pk).update(
            created_at=timezone.make_aware(timezone.datetime(2026, 1, 1))
        )

    new_apps = migrate(AFTER)

    assert sorted(numbers(new_apps, farm).values()) == [1, 2, 3]


def test_a_farm_without_plots_keeps_its_counter_at_zero(old_state):
    farm = make_farm(old_state, 1)

    new_apps = migrate(AFTER)

    assert new_apps.get_model("farms", "Farm").objects.get(pk=farm.pk).plot_sequence == 0


def test_the_migration_can_be_undone(old_state):
    farm = make_farm(old_state, 1)
    make_plot(old_state, farm, "Uno", age_days=1)
    migrate(AFTER)

    back = migrate(BEFORE)

    assert back.get_model("plots", "Plot").objects.count() == 1
