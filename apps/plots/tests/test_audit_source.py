"""Las parcelas en la bitácora: su etiqueta, sus cambios y el polígono sin valor."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.plots.models import PlotAuditEvent
from apps.plots.services.audit import record_plot_audit_event
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


def _describe(*events):
    return audit_source("plot").describe([event.pk for event in events])


def test_a_plot_is_named_by_its_code_and_its_name():
    plot = PlotFactory(name="Lote del río")
    event = record_plot_audit_event(plot=plot, actor=None, action="created")

    [entry] = _describe(event)

    assert entry.record_label == f"{plot.code} · Lote del río"
    assert entry.action_label == "Parcela creada"


def test_the_polygon_says_it_changed_without_its_value():
    plot = PlotFactory()
    event = record_plot_audit_event(
        plot=plot, actor=None, action="updated", changed_fields=["boundary"], before={}
    )

    [change] = _describe(event)[0].changes

    assert (change.label, change.before, change.after, change.hidden) == (
        "Polígono",
        None,
        None,
        "not_shown",
    )


def test_a_deleted_plot_keeps_its_code():
    plot = PlotFactory()
    event = record_plot_audit_event(plot=plot, actor=None, action="deleted")
    PlotAuditEvent.objects.filter(pk=event.pk).update(plot=None)

    [entry] = _describe(event)

    assert (entry.record_label, entry.record_deleted) == (plot.code, True)


def test_the_events_are_only_those_of_the_producer():
    mine = record_plot_audit_event(plot=PlotFactory(), actor=None, action="created")
    record_plot_audit_event(plot=PlotFactory(), actor=None, action="created")

    assert [row["id"] for row in audit_source("plot").events(mine.producer_ref)] == [mine.pk]
