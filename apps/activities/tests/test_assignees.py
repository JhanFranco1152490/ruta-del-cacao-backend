import pytest

from apps.accounts.system_roles import FOREMAN, SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.activities.exceptions import InvalidActivity
from apps.activities.services.queries import assignable_account, assignee_options
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

COMPLETE = "activities.complete_agriculturalactivity"


@pytest.fixture
def producer():
    return ProducerFactory()


def names(options):
    return [option["full_name"] for option in options]


def test_it_lists_the_accounts_of_the_producer_by_surname(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Zapata")
    UserFactory(producer=producer, first_name="Luis", last_name="Gómez")
    UserFactory(producer=ProducerFactory(), first_name="Otro", last_name="Productor")

    assert names(assignee_options(actor)) == ["Luis Gómez", "Ana Zapata"]


def test_inactive_accounts_are_listed_and_marked(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Activa")
    UserFactory(producer=producer, first_name="Ina", last_name="Inactiva", is_active=False)

    options = {option["full_name"]: option["is_active"] for option in assignee_options(actor)}

    assert options == {"Ana Activa": True, "Ina Inactiva": False}


def test_only_what_is_needed_to_assign_is_given(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Zapata")

    [option] = assignee_options(actor)

    # Ni el documento ni los roles: quien asigna no tiene por qué verlos.
    assert set(option) == {"id", "full_name", "is_active", "farm_ids", "assignable"}
    assert option["id"] == actor.pk


def test_an_account_without_a_name_is_shown_by_its_email(producer):
    actor = UserFactory(producer=producer, first_name="", last_name="", email="sin@example.com")

    assert names(assignee_options(actor)) == ["sin@example.com"]


def test_a_producer_sent_by_another_account_is_ignored(producer):
    actor = UserFactory(producer=producer, first_name="Ana", last_name="Zapata")
    UserFactory(producer=ProducerFactory(), first_name="Otro", last_name="Productor")

    assert names(assignee_options(actor, producer_id=ProducerFactory().pk)) == ["Ana Zapata"]


def test_the_technical_account_chooses_the_producer(producer):
    UserFactory(producer=producer, first_name="Ana", last_name="Zapata")
    superuser = UserFactory(is_superuser=True)

    assert names(assignee_options(superuser, producer_id=producer.pk)) == ["Ana Zapata"]


def test_the_technical_account_must_say_which_producer():
    with pytest.raises(InvalidActivity) as error:
        assignee_options(UserFactory(is_superuser=True))

    assert "producer" in error.value.fields


def test_an_account_without_a_producer_gets_nobody():
    UserFactory(producer=ProducerFactory())

    assert assignee_options(UserFactory()) == []


# --- A quién se le asigna ---


class Team:
    """Un productor con dos fincas, su capataz en cada una y gente que no hace labores."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm = FarmFactory(producer=self.producer)
        self.other_farm = FarmFactory(producer=self.producer)
        self.plot = PlotFactory(farm=self.farm)
        self.owner = make_producer_owner(self.producer)
        foreman = get_system_role(FOREMAN)
        self.foreman = grant_role(UserFactory(producer=self.producer, farm=self.farm), foreman)
        self.worker = make_delegate(self.producer, [COMPLETE], farm=self.farm)
        self.elsewhere = grant_role(
            UserFactory(producer=self.producer, farm=self.other_farm), foreman
        )
        self.seller = grant_role(
            UserFactory(producer=self.producer, farm=self.farm), get_system_role(SALES_MANAGER)
        )
        self.unassigned = make_delegate(self.producer, [COMPLETE])


@pytest.fixture
def team():
    return Team()


def options_by_id(actor):
    return {option["id"]: option for option in assignee_options(actor)}


def test_the_producer_can_assign_to_its_field_people_and_to_itself(team):
    options = options_by_id(team.owner)

    assignable = {account_id for account_id, option in options.items() if option["assignable"]}
    assert assignable == {team.owner.pk, team.foreman.pk, team.worker.pk, team.elsewhere.pk}
    # Sigue en la lista, para el filtro del calendario, pero no se le asignan labores: su rol no
    # registra realizaciones. Vale igual para un rol propio sin ese permiso.
    assert options[team.seller.pk]["assignable"] is False
    # Un empleado sin finca no trabaja en ninguna.
    assert options[team.unassigned.pk]["assignable"] is False


def test_each_account_carries_the_farm_it_works_in(team):
    options = options_by_id(team.owner)

    assert options[team.foreman.pk]["farm_ids"] == [team.farm.pk]
    assert options[team.elsewhere.pk]["farm_ids"] == [team.other_farm.pk]
    # El Productor vale para todas sus fincas.
    assert options[team.owner.pk]["farm_ids"] == []


def test_a_foreman_gets_its_farm_and_the_producer_but_cannot_assign_to_the_producer(team):
    options = options_by_id(team.foreman)

    assert set(options) == {team.owner.pk, team.foreman.pk, team.worker.pk, team.seller.pk}
    assert options[team.foreman.pk]["assignable"] is True
    assert options[team.worker.pk]["assignable"] is True
    # Un empleado no le pone labores a quien lo dirige.
    assert options[team.owner.pk]["assignable"] is False


@pytest.mark.parametrize(
    ("actor", "account", "accepted"),
    [
        ("owner", "foreman", True),
        ("owner", "worker", True),
        ("owner", "owner", True),
        ("owner", "elsewhere", False),
        ("owner", "seller", False),
        ("owner", "unassigned", False),
        ("foreman", "foreman", True),
        ("foreman", "worker", True),
        ("foreman", "owner", False),
        ("foreman", "elsewhere", False),
    ],
)
def test_who_can_be_made_responsible_on_a_plot(team, actor, account, accepted):
    found = assignable_account(getattr(team, actor), team.plot, getattr(team, account).pk)

    assert (found is not None) is accepted


def test_an_inactive_account_is_not_assigned(team):
    team.worker.is_active = False
    team.worker.save(update_fields=["is_active"])

    assert assignable_account(team.owner, team.plot, team.worker.pk) is None


def test_an_account_of_another_producer_is_not_assigned(team):
    stranger = make_producer_owner(ProducerFactory())

    assert assignable_account(team.owner, team.plot, stranger.pk) is None


def test_the_technical_account_assigns_to_the_producer(team):
    superuser = UserFactory(is_superuser=True)

    assert assignable_account(superuser, team.plot, team.owner.pk) == team.owner


def test_someone_who_works_in_two_farms_is_assigned_in_both(team):
    both = make_delegate(team.producer, [COMPLETE], farms=[team.farm, team.other_farm])
    plot_elsewhere = PlotFactory(farm=team.other_farm)

    assert assignable_account(team.owner, team.plot, both.pk) == both
    assert assignable_account(team.owner, plot_elsewhere, both.pk) == both
    # El capataz de la primera finca lo ve: comparten una.
    assert both.pk in options_by_id(team.foreman)
