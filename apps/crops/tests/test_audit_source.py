"""La ficha de la parcela en la bitácora: cada versión comparada con la anterior."""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.contracts.audit_log import audit_source
from apps.crops.models import PlotCharacterizationAuditEvent
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

PLANTING = {
    "variety_id": "v1",
    "name": "CCN-51",
    "planting_date": "2017-04",
    "tree_count": 1800,
    "propagation": "grafted",
    "stage": "full_production",
}


def _version(plot, version, shade, plantings=(PLANTING,)):
    return PlotCharacterizationAuditEvent.objects.create(
        plot=plot,
        producer_ref=plot.farm.producer_id,
        actor=UserFactory(),
        action="created" if version == 1 else "updated",
        version=version,
        snapshot={
            "plantings": list(plantings),
            "management_system": "conventional",
            "shade_type": shade,
        },
    )


def _describe(*events):
    return audit_source("plot_characterization").describe([event.pk for event in events])


def test_the_first_version_brings_what_it_had():
    plot = PlotFactory()
    first = _version(plot, 1, "permanent")

    [entry] = _describe(first)

    assert entry.record_label == f"Ficha de {plot.code}"
    changes = {change.field: change for change in entry.changes}
    assert changes["shade_type"].before is None
    assert changes["shade_type"].after == "Sombra permanente"
    assert changes["plantings"].after == (
        "CCN-51: 1800 árboles, sembrada en 2017-04, Injerto o clon, Producción estable"
    )


def test_a_later_version_shows_only_what_changed_from_the_previous_one():
    plot = PlotFactory()
    _version(plot, 1, "permanent")
    second = _version(plot, 2, "mixed")

    [entry] = _describe(second)

    [change] = entry.changes
    assert (change.label, change.before, change.after) == (
        "Sombra",
        "Sombra permanente",
        "Temporal y permanente",
    )


def test_many_versions_take_the_same_queries(django_assert_num_queries):
    plot = PlotFactory()
    events = [_version(plot, version, "permanent") for version in range(1, 31)]

    with django_assert_num_queries(2):
        entries = _describe(*events)

    assert len(entries) == 30
