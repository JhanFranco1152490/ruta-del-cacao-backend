import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.db import has_dependent_rows
from apps.farms.models import FarmAuditEvent
from apps.farms.services.audit import record_farm_audit_event
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import PlotAuditEvent
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


def test_a_row_without_dependents_has_none():
    assert has_dependent_rows(FarmFactory()) is False


@pytest.mark.parametrize("is_active", [True, False])
def test_any_row_pointing_to_it_counts_active_or_not(is_active):
    plot = PlotFactory(is_active=is_active)

    assert has_dependent_rows(plot.farm) is True


def test_the_ignored_tables_do_not_count():
    farm = FarmFactory()
    record_farm_audit_event(farm=farm, actor=UserFactory(), action=FarmAuditEvent.Action.CREATED)

    assert has_dependent_rows(farm) is True
    assert has_dependent_rows(farm, ignore=(FarmAuditEvent,)) is False


def test_a_plot_with_only_its_history_has_no_dependents():
    plot = PlotFactory()
    PlotAuditEvent.record(
        plot=plot,
        plot_ref=plot.pk,
        plot_code=plot.code,
        actor=UserFactory(),
        action=PlotAuditEvent.Action.CREATED,
        area_hectares=plot.area_hectares,
    )

    assert has_dependent_rows(plot, ignore=(PlotAuditEvent,)) is False
