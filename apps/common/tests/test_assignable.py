"""La regla de quién puede responder por una labor en una finca, probada con dos permisos distintos
para dejar claro que solo cambia el permiso."""

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.common.contracts.assignable import assignable_person, person_options
from apps.common.exceptions import ProducerRequired
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

COMPLETE = "activities.complete_agriculturalactivity"
STOCK = "inputs.manage_inputstock"


@pytest.fixture
def producer():
    return ProducerFactory()


def options(actor, permission=COMPLETE, producer_id=None):
    return {
        option["id"]: option
        for option in person_options(
            actor, producer_id, permission, producer_required=ProducerRequired
        )
    }


@pytest.mark.parametrize("permission", [COMPLETE, STOCK])
def test_only_who_has_the_permission_can_be_assigned(producer, permission):
    farm = FarmFactory(producer=producer)
    owner = make_producer_owner(producer)
    allowed = make_delegate(producer, [permission], farm=farm)
    without = make_delegate(producer, ["plots.view_plot"], farm=farm)

    found = options(owner, permission)

    assert found[allowed.pk]["assignable"] is True
    assert found[without.pk]["assignable"] is False


def test_the_permission_of_one_labor_does_not_serve_another(producer):
    farm = FarmFactory(producer=producer)
    owner = make_producer_owner(producer)
    worker = make_delegate(producer, [COMPLETE], farm=farm)

    assert options(owner, COMPLETE)[worker.pk]["assignable"] is True
    assert options(owner, STOCK)[worker.pk]["assignable"] is False


def test_an_employee_is_only_offered_for_the_farms_they_work_in(producer):
    farm, other = FarmFactory(producer=producer), FarmFactory(producer=producer)
    owner = make_producer_owner(producer)
    worker = make_delegate(producer, [COMPLETE], farm=farm)

    found = options(owner)

    assert found[worker.pk]["farm_ids"] == [farm.pk]
    assert assignable_person(owner, PlotFactory(farm=farm), worker.pk, COMPLETE) == worker
    assert assignable_person(owner, PlotFactory(farm=other), worker.pk, COMPLETE) is None


def test_the_producer_is_assigned_only_by_itself_or_the_technical_account(producer):
    farm = FarmFactory(producer=producer)
    owner = make_producer_owner(producer)
    foreman = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))
    plot = PlotFactory(farm=farm)

    assert assignable_person(owner, plot, owner.pk, COMPLETE) == owner
    assert assignable_person(foreman, plot, owner.pk, COMPLETE) is None
    assert assignable_person(UserFactory(is_superuser=True), plot, owner.pk, COMPLETE) == owner


def test_an_inactive_account_is_listed_but_never_assignable(producer):
    farm = FarmFactory(producer=producer)
    owner = make_producer_owner(producer)
    worker = make_delegate(producer, [COMPLETE], farm=farm)
    worker.is_active = False
    worker.save()

    assert options(owner)[worker.pk]["is_active"] is False
    assert assignable_person(owner, PlotFactory(farm=farm), worker.pk, COMPLETE) is None


def test_an_account_of_another_producer_is_never_assignable(producer):
    owner = make_producer_owner(producer)
    stranger = make_producer_owner(ProducerFactory())

    assert (
        assignable_person(
            owner, PlotFactory(farm=FarmFactory(producer=producer)), stranger.pk, COMPLETE
        )
        is None
    )


def test_the_technical_account_must_say_which_producer():
    with pytest.raises(ProducerRequired):
        options(UserFactory(is_superuser=True))


def test_the_technical_account_lists_the_producer_it_names(producer):
    owner = make_producer_owner(producer)

    assert owner.pk in options(UserFactory(is_superuser=True), producer_id=producer.pk)


def test_an_account_without_a_producer_gets_nobody():
    assert options(UserFactory()) == {}
