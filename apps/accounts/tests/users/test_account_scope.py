"""«Todas las fincas» y el alcance que admite cada rol: qué se puede dar, quién lo da y qué se
rechaza."""

from datetime import timedelta

import pytest

from apps.accounts.models import Role, User
from apps.accounts.system_roles import FOREMAN, SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

USERS_URL = "/api/users"
TRUSTED = [
    "accounts.users_view",
    "accounts.users_create",
    "accounts.users_update",
    "accounts.roles_view",
    "farms.view_farm",
    "plots.view_plot",
]


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer, name="La Esperanza")


@pytest.fixture
def other_farm(producer):
    return FarmFactory(producer=producer, name="El Recreo")


def user_url(user) -> str:
    return f"{USERS_URL}/{user.pk}"


def body(*roles, **overrides) -> dict:
    data = {
        "email": "empleado@example.com",
        "document_type": "CC",
        "identity_document": "12345678",
        "first_name": "Luis",
        "last_name": "Gómez",
        "role_ids": [str(role.id) for role in roles],
    }
    data.update(overrides)
    return data


def many_role(producer, **kwargs):
    return RoleFactory(producer=producer, permissions=["plots.view_plot"], **kwargs)


# --- Crear con un alcance ---


def test_an_employee_is_created_working_in_all_the_farms(auth_client, owner, producer):
    response = auth_client(owner).post(
        USERS_URL, body(many_role(producer), all_farms=True), format="json"
    )

    assert response.status_code == 201
    assert response.data["all_farms"] is True
    assert response.data["farms"] == []
    assert response.data["needs_farm"] is False
    assert User.objects.get(pk=response.data["id"]).all_farms is True


def test_all_farms_and_a_list_of_farms_are_not_sent_together(auth_client, owner, producer, farm):
    response = auth_client(owner).post(
        USERS_URL,
        body(many_role(producer), all_farms=True, farm_ids=[str(farm.pk)]),
        format="json",
    )

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]


def test_a_role_that_takes_one_farm_does_not_take_two_or_all(
    auth_client, owner, producer, farm, other_farm
):
    foreman = get_system_role(FOREMAN)
    client = auth_client(owner)

    two = client.post(
        USERS_URL, body(foreman, farm_ids=[str(farm.pk), str(other_farm.pk)]), format="json"
    )
    everywhere = client.post(USERS_URL, body(foreman, all_farms=True), format="json")
    one = client.post(USERS_URL, body(foreman, farm_ids=[str(farm.pk)]), format="json")

    assert two.status_code == 400
    assert "farm_ids" in two.data["fields"]
    assert everywhere.status_code == 400
    assert "all_farms" in everywhere.data["fields"]
    assert one.status_code == 201


def test_a_role_that_asks_for_all_farms_does_not_take_a_list(auth_client, owner, producer, farm):
    role = many_role(producer, farm_scope=Role.FarmScope.ALL)
    client = auth_client(owner)

    listed = client.post(USERS_URL, body(role, farm_ids=[str(farm.pk)]), format="json")
    everywhere = client.post(USERS_URL, body(role, all_farms=True), format="json")

    assert listed.status_code == 400
    assert "all_farms" in listed.data["fields"]
    assert everywhere.status_code == 201


def test_roles_that_ask_for_all_and_for_one_farm_cannot_go_together(auth_client, owner, producer):
    all_role = many_role(producer, farm_scope=Role.FarmScope.ALL)
    one_role = many_role(producer, farm_scope=Role.FarmScope.ONE)

    response = auth_client(owner).post(
        USERS_URL, body(all_role, one_role, all_farms=True), format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "role_scope_conflict"


def test_a_role_that_takes_many_farms_adapts_to_the_one_that_asks(
    auth_client, owner, producer, farm
):
    free = many_role(producer)
    one = many_role(producer, farm_scope=Role.FarmScope.ONE)

    response = auth_client(owner).post(
        USERS_URL, body(free, one, farm_ids=[str(farm.pk)]), format="json"
    )

    assert response.status_code == 201


# --- Quién da qué alcance ---


def test_a_limited_employee_cannot_give_all_the_farms(auth_client, producer, farm):
    trusted = make_delegate(producer, TRUSTED, farm=farm)

    response = auth_client(trusted).post(
        USERS_URL, body(many_role(producer), all_farms=True), format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert not User.objects.filter(email="empleado@example.com").exists()


def test_a_limited_employee_cannot_assign_a_role_that_asks_for_all_the_farms(
    auth_client, producer, farm
):
    trusted = make_delegate(producer, TRUSTED, farm=farm)
    role = many_role(producer, farm_scope=Role.FarmScope.ALL)

    response = auth_client(trusted).post(
        USERS_URL, body(role, farm_ids=[str(farm.pk)]), format="json"
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="empleado@example.com").exists()


def test_an_employee_with_all_the_farms_gives_any_scope(auth_client, producer, farm, other_farm):
    trusted = make_delegate(producer, TRUSTED, all_farms=True)
    role = many_role(producer)
    client = auth_client(trusted)

    everywhere = client.post(USERS_URL, body(role, all_farms=True), format="json")
    other = client.post(
        USERS_URL,
        body(
            role,
            email="otra@example.com",
            identity_document="87654321",
            farm_ids=[str(other_farm.pk)],
        ),
        format="json",
    )

    assert everywhere.status_code == 201
    assert other.status_code == 201


# --- Cambiar el alcance ---


def test_the_producer_moves_an_employee_between_all_the_farms_and_some(
    auth_client, owner, producer, farm
):
    employee = grant_role(UserFactory(producer=producer, farm=farm), many_role(producer))
    client = auth_client(owner)

    everywhere = client.patch(user_url(employee), {"all_farms": True}, format="json")
    back = client.patch(user_url(employee), {"farm_ids": [str(farm.pk)]}, format="json")

    assert everywhere.status_code == 200
    assert everywhere.data["all_farms"] is True and everywhere.data["farms"] == []
    assert back.status_code == 200
    assert back.data["all_farms"] is False
    assert [row["id"] for row in back.data["farms"]] == [str(farm.pk)]


def test_a_limited_employee_does_not_change_the_scope_of_an_account(auth_client, producer, farm):
    trusted = make_delegate(producer, TRUSTED, farm=farm)
    colleague = grant_role(UserFactory(producer=producer, farm=farm), many_role(producer))

    response = auth_client(trusted).patch(user_url(colleague), {"all_farms": True}, format="json")

    assert response.status_code == 403


def test_an_employee_with_all_the_farms_can_change_the_scope_it_was_delegated(
    auth_client, producer, farm
):
    trusted = make_delegate(producer, TRUSTED, all_farms=True)
    colleague = grant_role(UserFactory(producer=producer, farm=farm), many_role(producer))

    response = auth_client(trusted).patch(user_url(colleague), {"all_farms": True}, format="json")

    assert response.status_code == 200


def test_leaving_all_the_farms_waits_for_the_labors_in_the_farms_that_remain_out(
    auth_client, owner, producer, farm, other_farm
):
    employee = grant_role(UserFactory(producer=producer, all_farms=True), many_role(producer))
    AgriculturalActivityFactory(
        plot=PlotFactory(farm=other_farm),
        assignee=employee,
        scheduled_date=today_in_bogota() + timedelta(days=5),
    )
    client = auth_client(owner)

    blocked = client.patch(user_url(employee), {"farm_ids": [str(farm.pk)]}, format="json")
    allowed = client.patch(user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json")

    assert (blocked.status_code, blocked.data["code"]) == (409, "account_has_pending_work")
    assert blocked.data["pending"] == 1
    assert allowed.status_code == 200


def test_changing_the_roles_checks_the_scope_the_account_already_has(
    auth_client, owner, producer, farm, other_farm
):
    employee = grant_role(
        UserFactory(producer=producer, farms=[farm, other_farm]), many_role(producer)
    )
    foreman = get_system_role(FOREMAN)
    client = auth_client(owner)

    rejected = client.put(
        f"{user_url(employee)}/roles", {"role_ids": [str(foreman.id)]}, format="json"
    )
    accepted = client.put(
        f"{user_url(employee)}/roles",
        {"role_ids": [str(foreman.id)], "farm_ids": [str(farm.pk)]},
        format="json",
    )

    assert rejected.status_code == 400
    assert accepted.status_code == 200


# --- Lo que se ve ---


def test_an_employee_without_scope_only_sees_its_own_account(auth_client, producer):
    delegate = make_delegate(producer, ["accounts.users_view"])
    other = grant_role(UserFactory(producer=producer, all_farms=True), many_role(producer))
    client = auth_client(delegate)

    listed = {row["id"] for row in client.get(USERS_URL).data["results"]}

    assert listed == {str(delegate.pk)}
    assert client.get(user_url(other)).status_code == 404


def test_an_employee_with_all_the_farms_sees_every_account_of_the_producer(
    auth_client, owner, producer, farm, other_farm
):
    delegate = make_delegate(producer, ["accounts.users_view"], all_farms=True)
    here = grant_role(UserFactory(producer=producer, farm=farm), many_role(producer))
    there = grant_role(UserFactory(producer=producer, farm=other_farm), many_role(producer))

    listed = {row["id"] for row in auth_client(delegate).get(USERS_URL).data["results"]}

    assert {str(here.pk), str(there.pk), str(delegate.pk)} <= listed
    assert str(owner.pk) in listed


def test_a_limited_employee_also_sees_who_works_in_all_the_farms(auth_client, producer, farm):
    viewer = make_delegate(producer, ["accounts.users_view"], farm=farm)
    everywhere = grant_role(UserFactory(producer=producer, all_farms=True), many_role(producer))
    elsewhere = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)), many_role(producer)
    )

    listed = {row["id"] for row in auth_client(viewer).get(USERS_URL).data["results"]}

    assert str(everywhere.pk) in listed
    assert str(elsewhere.pk) not in listed


def test_an_employee_with_all_the_farms_sees_the_farms_registered_afterwards(
    auth_client, producer, farm
):
    viewer = make_delegate(producer, ["farms.view_farm"], all_farms=True)
    client = auth_client(viewer)
    before = client.get("/api/farms").data["results"]

    later = FarmFactory(producer=producer, name="Registrada después")
    after = {row["id"] for row in client.get("/api/farms").data["results"]}

    assert len(before) == 1
    assert str(later.pk) in after and str(farm.pk) in after


def test_the_session_says_when_an_employee_works_in_all_the_farms(auth_client, producer, farm):
    everywhere = make_delegate(producer, ["farms.view_farm"], all_farms=True)
    limited = make_delegate(producer, ["farms.view_farm"], farm=farm)

    assert auth_client(everywhere).get("/api/auth/me").data["user"]["all_farms"] is True
    assert auth_client(limited).get("/api/auth/me").data["user"]["all_farms"] is False


def test_the_producer_account_reaches_all_the_farms_without_the_mark(producer):
    owner = make_producer_owner(producer)

    assert owner.all_farms is False
    sales = get_system_role(SALES_MANAGER)
    assert sales.farm_scope == Role.FarmScope.MANY


def test_the_roles_of_an_account_say_what_scope_they_admit(auth_client, owner, producer, farm):
    foreman = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))
    client = auth_client(owner)

    assert client.get(user_url(foreman)).data["roles"][0]["farm_scope"] == "one"
    # El Productor no lleva fincas: su rol no dice alcance.
    assert client.get(user_url(owner)).data["roles"][0]["farm_scope"] is None
