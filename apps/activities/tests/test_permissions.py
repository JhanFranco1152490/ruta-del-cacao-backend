import pytest

from apps.accounts.registry import area_of, is_delegable, with_dependencies
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    SALES_MANAGER,
    SYSTEM_ROLES,
)

VIEW = "activities.view_agriculturalactivity"
ADD = "activities.add_agriculturalactivity"
CHANGE = "activities.change_agriculturalactivity"
COMPLETE = "activities.complete_agriculturalactivity"
DELETE = "activities.delete_agriculturalactivity"
ALL = {VIEW, ADD, CHANGE, COMPLETE, DELETE}


@pytest.mark.parametrize("code", sorted(ALL))
def test_every_activity_permission_is_delegable_and_grouped(code):
    assert is_delegable(code)
    assert area_of(code) == "activities"


@pytest.mark.parametrize("code", sorted(ALL - {VIEW}))
def test_each_action_brings_what_it_needs_to_see(code):
    # Las actividades se programan y se consultan en una parcela de una finca: sin verlas no hay
    # cómo llegar a ellas.
    assert with_dependencies({code}) == {code, VIEW, "plots.view_plot", "farms.view_farm"}


def test_the_producer_has_every_activity_permission():
    assert ALL <= set(SYSTEM_ROLES[PRODUCER]["permissions"])


def test_the_foreman_plans_and_records_but_does_not_delete():
    granted = set(SYSTEM_ROLES[FOREMAN]["permissions"])

    assert granted & ALL == {VIEW, ADD, CHANGE, COMPLETE}


def test_the_foreman_reads_the_farms_and_plots_it_schedules_on():
    granted = set(SYSTEM_ROLES[FOREMAN]["permissions"])

    assert {"farms.view_farm", "plots.view_plot"} <= granted
    assert not granted & {"farms.add_farm", "farms.change_farm", "farms.delete_farm"}
    assert not granted & {"plots.add_plot", "plots.change_plot", "plots.delete_plot"}


@pytest.mark.parametrize("code", [ADMINISTRATOR, QUALITY_MANAGER, SALES_MANAGER])
def test_the_other_system_roles_have_no_activity_permission(code):
    assert not set(SYSTEM_ROLES[code]["permissions"]) & ALL
