"""La migración que mueve la etapa de la ficha a cada siembra, probada con datos del estado
anterior: se vuelve a ese estado, se crean fichas con la forma vieja y se migra hacia adelante."""

from datetime import date
from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.crops.models import PlotCharacterization, PlotCharacterizationAuditEvent, PlotPlanting
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [("crops", "0004_seed_common_names")]
AFTER = [("crops", "0005_stage_per_planting_and_event_version")]

migration = import_module("apps.crops.migrations.0005_stage_per_planting_and_event_version")


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


@pytest.fixture
def old_state():
    """El estado anterior a la migración; al terminar, la base vuelve al más nuevo."""
    old_apps = migrate(BEFORE)
    yield old_apps
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def make_old_variety(old_apps, name):
    # El catálogo inicial ya viene cargado por sus migraciones: se reutiliza si existe.
    variety, _ = old_apps.get_model("crops", "CacaoVariety").objects.get_or_create(
        name_normalized=migration._normalize(name),
        defaults={"name": name, "search_normalized": migration._normalize(name)},
    )
    return variety


def make_old_characterization(old_apps, plot, stage, plantings):
    characterization = old_apps.get_model("crops", "PlotCharacterization").objects.create(
        plot_id=plot.pk, stage=stage
    )
    for variety, planting_date, trees in plantings:
        old_apps.get_model("crops", "PlotPlanting").objects.create(
            characterization=characterization,
            variety=variety,
            planting_date=planting_date,
            tree_count=trees,
        )
    return characterization


def test_every_planting_takes_the_stage_of_its_characterization(old_state):
    clone = make_old_variety(old_state, "CCN-51")
    plot = PlotFactory()
    make_old_characterization(
        old_state,
        plot,
        "renovation",
        [(clone, date(2018, 4, 1), 1000), (clone, date(2024, 2, 1), 500)],
    )

    migrate(AFTER)

    assert set(PlotPlanting.objects.values_list("stage", flat=True)) == {"renovation"}


def test_the_propagation_comes_from_the_variety(old_state):
    clone = make_old_variety(old_state, "CCN-51")
    hybrid = make_old_variety(old_state, "Híbrido o común (sin identificar)")
    plot = PlotFactory()
    make_old_characterization(
        old_state,
        plot,
        "full_production",
        [(clone, date(2018, 4, 1), 1000), (hybrid, date(2015, 1, 1), 300)],
    )

    migrate(AFTER)

    assert dict(PlotPlanting.objects.values_list("variety__name", "propagation")) == {
        "CCN-51": "grafted",
        "Híbrido o común (sin identificar)": "seed",
    }


def test_existing_events_are_numbered_by_order_within_each_plot(old_state):
    first, second = PlotFactory(), PlotFactory()
    Event = old_state.get_model("crops", "PlotCharacterizationAuditEvent")
    for plot, minute in ((first, 1), (second, 2), (first, 3), (first, 4), (second, 5)):
        event = Event.objects.create(plot_id=plot.pk, action="updated", snapshot={})
        Event.objects.filter(pk=event.pk).update(occurred_at=f"2026-10-03T14:0{minute}:00Z")

    migrate(AFTER)

    versions = lambda plot: list(  # noqa: E731
        PlotCharacterizationAuditEvent.objects.filter(plot=plot)
        .order_by("occurred_at")
        .values_list("version", flat=True)
    )
    assert versions(first) == [1, 2, 3]
    assert versions(second) == [1, 2]


def test_reverting_gives_the_characterization_the_stage_of_its_largest_planting(old_state):
    clone = make_old_variety(old_state, "CCN-51")
    plot = PlotFactory()
    make_old_characterization(
        old_state, plot, "full_production", [(clone, date(2018, 4, 1), 1000)]
    )
    migrate(AFTER)
    PlotPlanting.objects.update(stage="establishment")
    PlotPlanting.objects.create(
        characterization=PlotCharacterization.objects.get(),
        variety_id=PlotPlanting.objects.get().variety_id,
        planting_date=date(2024, 2, 1),
        tree_count=3000,
        propagation="grafted",
        stage="renovation",
    )

    old_apps = migrate(BEFORE)

    stage = old_apps.get_model("crops", "PlotCharacterization").objects.get().stage
    assert stage == "renovation"


def test_existing_snapshots_move_the_stage_to_each_planting(old_state):
    clone = make_old_variety(old_state, "CCN-51")
    hybrid = make_old_variety(old_state, "Híbrido o común (sin identificar)")
    plot = PlotFactory()
    old_row = {"planting_date": "2021-03", "tree_count": 900}
    old_apps_event = old_state.get_model("crops", "PlotCharacterizationAuditEvent")
    old_apps_event.objects.create(
        plot_id=plot.pk,
        action="created",
        snapshot={
            "stage": "renovation",
            "management_system": None,
            "shade_type": None,
            "plantings": [
                {"variety_id": str(clone.pk), "name": "CCN-51", **old_row},
                {"variety_id": str(hybrid.pk), "name": hybrid.name, **old_row},
            ],
        },
    )

    migrate(AFTER)

    snapshot = PlotCharacterizationAuditEvent.objects.get().snapshot
    assert "stage" not in snapshot
    assert [(row["name"], row["stage"], row["propagation"]) for row in snapshot["plantings"]] == [
        ("CCN-51", "renovation", "grafted"),
        (hybrid.name, "renovation", "seed"),
    ]
    assert snapshot["management_system"] is None


def test_a_snapshot_already_in_the_new_shape_is_left_alone(old_state):
    plot = PlotFactory()
    new_shape = {"plantings": [], "management_system": None, "shade_type": None}
    old_state.get_model("crops", "PlotCharacterizationAuditEvent").objects.create(
        plot_id=plot.pk, action="created", snapshot=new_shape
    )

    migrate(AFTER)

    assert PlotCharacterizationAuditEvent.objects.get().snapshot == new_shape
