"""Los valores en el historial de la parcela, sin el polígono, que no se copia: es grande y la
bitácora solo dice que cambió."""

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.plots.models import PlotAuditEvent
from apps.plots.services.audit import VALUE_FIELDS, record_plot_audit_event
from apps.plots.services.update import update_plot
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


def _last(plot, action):
    return PlotAuditEvent.objects.filter(plot_ref=plot.pk, action=action).latest("occurred_at")


def test_an_edit_keeps_the_previous_and_the_new_value():
    plot = PlotFactory(name="Lote del río")
    owner = make_producer_owner(plot.farm.producer)

    update_plot(owner, plot.pk, plot.version, {"name": "Lote de la quebrada"})

    assert _last(plot, "updated").changes == {
        "name": {"before": "Lote del río", "after": "Lote de la quebrada"}
    }


def test_the_polygon_is_kept_by_name_without_its_value():
    plot = PlotFactory()

    record_plot_audit_event(
        plot=plot, actor=None, action="updated", changed_fields=["boundary"], before={}
    )

    event = _last(plot, "updated")
    assert event.changed_fields == ["boundary"]
    assert event.changes == {}


def test_a_creation_keeps_every_value_without_the_polygon():
    plot = PlotFactory(name="Lote del río")

    record_plot_audit_event(plot=plot, actor=None, action="created")

    changes = _last(plot, "created").changes
    assert set(changes) == set(VALUE_FIELDS)
    assert "boundary" not in VALUE_FIELDS
    assert changes["name"] == {"before": None, "after": "Lote del río"}
