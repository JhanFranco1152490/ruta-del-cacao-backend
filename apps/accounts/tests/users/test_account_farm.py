"""La finca de un empleado: quién la asigna, cuándo es obligatoria y qué deja ver."""

from datetime import timedelta

import pytest

from apps.accounts.models import AccountManagementEvent, User
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory, done_activity
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

USERS_URL = "/api/users"
FARM_CHANGED = AccountManagementEvent.EventType.ACCOUNT_FARM_CHANGED


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


def employee_body(role, **overrides) -> dict:
    body = {
        "email": "empleado@example.com",
        "document_type": "CC",
        "identity_document": "12345678",
        "first_name": "Luis",
        "last_name": "Gómez",
        "role_ids": [str(role.id)],
    }
    body.update(overrides)
    return body


def make_foreman(producer, farm=None):
    return grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))


# --- Crear ---


def test_an_employee_with_field_permissions_is_created_in_its_farm(auth_client, owner, farm):
    response = auth_client(owner).post(
        USERS_URL, employee_body(get_system_role(FOREMAN), farm_ids=[str(farm.pk)]), format="json"
    )

    assert response.status_code == 201
    assert response.data["farms"] == [
        {"id": str(farm.pk), "name": "La Esperanza", "is_active": True}
    ]
    assert response.data["needs_farm"] is False
    assert list(User.objects.get(pk=response.data["id"]).farms.all()) == [farm]


def test_an_employee_with_field_permissions_needs_a_farm(auth_client, owner, farm):
    response = auth_client(owner).post(
        USERS_URL, employee_body(get_system_role(FOREMAN)), format="json"
    )

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]
    assert not User.objects.filter(email="empleado@example.com").exists()


def test_every_employee_needs_a_scope_even_without_field_permissions(auth_client, owner):
    response = auth_client(owner).post(
        USERS_URL, employee_body(get_system_role(SALES_MANAGER)), format="json"
    )

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]
    assert not User.objects.filter(email="empleado@example.com").exists()


def test_an_employee_without_field_permissions_may_work_in_all_the_farms(auth_client, owner):
    response = auth_client(owner).post(
        USERS_URL, employee_body(get_system_role(SALES_MANAGER), all_farms=True), format="json"
    )

    assert response.status_code == 201
    assert response.data["farms"] == []
    assert response.data["all_farms"] is True
    assert response.data["needs_farm"] is False


@pytest.mark.parametrize("case", ["another_producer", "inactive", "unknown"])
def test_the_farm_must_be_an_active_one_of_the_producer(auth_client, owner, producer, case):
    farm_id = {
        "another_producer": lambda: FarmFactory().pk,
        "inactive": lambda: FarmFactory(producer=producer, is_active=False).pk,
        "unknown": lambda: "7c1f2f0e-0000-4000-8000-000000000000",
    }[case]()

    response = auth_client(owner).post(
        USERS_URL, employee_body(get_system_role(FOREMAN), farm_ids=[str(farm_id)]), format="json"
    )

    assert response.status_code == 400
    # El mismo mensaje en los tres casos: no confirma que la finca de otro productor existe.
    assert response.data["fields"]["farm_ids"] == ["Elige fincas activas del productor."]


TRUSTED = [
    "accounts.users_view",
    "accounts.users_create",
    "accounts.users_update",
    "accounts.roles_view",
    "farms.view_farm",
    "plots.view_plot",
]


def test_a_trusted_employee_creates_accounts_in_its_own_farm(auth_client, producer, farm):
    # El Productor le delegó crear cuentas en un rol propio; la finca la toma de quien la crea.
    trusted = make_delegate(producer, TRUSTED, farm=farm)
    field_role = RoleFactory(producer=producer, permissions=["plots.view_plot"])

    response = auth_client(trusted).post(USERS_URL, employee_body(field_role), format="json")

    assert response.status_code == 201
    assert [farm["id"] for farm in response.data["farms"]] == [str(farm.pk)]


def test_a_trusted_employee_cannot_create_accounts_for_another_farm(
    auth_client, producer, farm, other_farm
):
    trusted = make_delegate(producer, TRUSTED, farm=farm)
    field_role = RoleFactory(producer=producer, permissions=["plots.view_plot"])

    response = auth_client(trusted).post(
        USERS_URL, employee_body(field_role, farm_ids=[str(other_farm.pk)]), format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert not User.objects.filter(email="empleado@example.com").exists()


def test_registering_farms_can_be_granted_to_a_role(auth_client, owner):
    response = auth_client(owner).post(
        "/api/roles",
        {"name": "Encargado de fincas", "permission_codes": ["farms.add_farm"]},
        format="json",
    )

    assert response.status_code == 201
    assert sorted(response.data["permissions"]) == ["farms.add_farm", "farms.view_farm"]


def test_the_administrator_account_takes_no_farm(auth_client, farm):
    response = auth_client(make_administrator()).post(
        USERS_URL,
        employee_body(get_system_role(ADMINISTRATOR), farm_ids=[str(farm.pk)]),
        format="json",
    )

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]


# --- Cambiar ---


def test_the_producer_moves_an_employee_to_another_farm(auth_client, owner, farm, other_farm):
    employee = make_foreman(owner.producer, farm)

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json"
    )

    assert response.status_code == 200
    assert [farm["id"] for farm in response.data["farms"]] == [str(other_farm.pk)]
    employee.refresh_from_db()
    assert list(employee.farms.all()) == [other_farm]
    event = AccountManagementEvent.objects.get(event_type=FARM_CHANGED)
    assert (event.actor, event.target_user) == (owner, employee)


def test_sending_the_same_farm_leaves_no_event(auth_client, owner, farm):
    employee = make_foreman(owner.producer, farm)

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(farm.pk)]}, format="json"
    )

    assert response.status_code == 200
    assert not AccountManagementEvent.objects.filter(event_type=FARM_CHANGED).exists()


def test_the_farm_cannot_be_removed_while_the_roles_need_it(auth_client, owner, farm):
    employee = make_foreman(owner.producer, farm)

    response = auth_client(owner).patch(user_url(employee), {"farm_ids": []}, format="json")

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]
    employee.refresh_from_db()
    assert list(employee.farms.all()) == [farm]


def test_an_employee_cannot_be_left_without_scope(auth_client, owner, farm):
    employee = grant_role(
        UserFactory(producer=owner.producer, farm=farm), get_system_role(SALES_MANAGER)
    )

    response = auth_client(owner).patch(user_url(employee), {"farm_ids": []}, format="json")

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]
    assert list(employee.farms.all()) == [farm]


def test_an_employee_keeps_its_farm_after_it_is_deactivated(auth_client, owner, farm):
    employee = make_foreman(owner.producer, farm)
    farm.is_active = False
    farm.save(update_fields=["is_active"])

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(farm.pk)], "first_name": "Luisa"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["farms"][0]["is_active"] is False


def test_an_employee_that_edits_accounts_cannot_move_them(auth_client, producer, farm, other_farm):
    target = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(SALES_MANAGER))
    delegate = make_delegate(producer, ["accounts.users_update", "accounts.users_view"], farm=farm)

    response = auth_client(delegate).patch(
        user_url(target), {"farm_ids": [str(other_farm.pk)]}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    target.refresh_from_db()
    assert list(target.farms.all()) == [farm]


def test_the_producer_account_takes_no_farm(auth_client, producer, farm):
    owner = make_producer_owner(producer)

    response = auth_client(make_administrator()).patch(
        user_url(owner), {"farm_ids": [str(farm.pk)]}, format="json"
    )

    assert response.status_code == 400
    assert "farm_ids" in response.data["fields"]


# --- Cambiar los roles ---


def test_gaining_field_permissions_needs_the_farm_in_the_same_request(auth_client, owner, farm):
    employee = grant_role(UserFactory(producer=owner.producer), get_system_role(SALES_MANAGER))
    foreman = get_system_role(FOREMAN)
    client = auth_client(owner)

    without = client.put(
        f"{user_url(employee)}/roles", {"role_ids": [str(foreman.id)]}, format="json"
    )
    with_farm = client.put(
        f"{user_url(employee)}/roles",
        {"role_ids": [str(foreman.id)], "farm_ids": [str(farm.pk)]},
        format="json",
    )

    assert without.status_code == 400
    assert "farm_ids" in without.data["fields"]
    assert with_farm.status_code == 200
    assert [farm["id"] for farm in with_farm.data["farms"]] == [str(farm.pk)]
    assert AccountManagementEvent.objects.filter(event_type=FARM_CHANGED).count() == 1


def test_an_employee_with_a_farm_changes_roles_without_sending_it(auth_client, owner, farm):
    employee = make_foreman(owner.producer, farm)
    custom = RoleFactory(producer=owner.producer, permissions=["plots.view_plot"])

    response = auth_client(owner).put(
        f"{user_url(employee)}/roles", {"role_ids": [str(custom.id)]}, format="json"
    )

    assert response.status_code == 200
    assert [farm["id"] for farm in response.data["farms"]] == [str(farm.pk)]


# --- Lo que se ve ---


def test_needs_farm_marks_every_employee_without_a_scope(auth_client, owner, farm):
    pending = make_foreman(owner.producer)
    office = grant_role(UserFactory(producer=owner.producer), get_system_role(SALES_MANAGER))
    placed = make_foreman(owner.producer, farm)
    everywhere = grant_role(
        UserFactory(producer=owner.producer, all_farms=True), get_system_role(SALES_MANAGER)
    )
    client = auth_client(owner)

    assert client.get(user_url(pending)).data["needs_farm"] is True
    assert client.get(user_url(office)).data["needs_farm"] is True
    assert client.get(user_url(placed)).data["needs_farm"] is False
    assert client.get(user_url(everywhere)).data["needs_farm"] is False
    assert client.get(user_url(owner)).data["needs_farm"] is False


def test_the_list_filters_by_farm_and_by_missing_farm(auth_client, owner, farm, other_farm):
    here = make_foreman(owner.producer, farm)
    make_foreman(owner.producer, other_farm)
    pending = make_foreman(owner.producer)
    office = grant_role(UserFactory(producer=owner.producer), get_system_role(SALES_MANAGER))
    everywhere = grant_role(
        UserFactory(producer=owner.producer, all_farms=True), get_system_role(SALES_MANAGER)
    )
    client = auth_client(owner)

    def ids(**params):
        return {row["id"] for row in client.get(USERS_URL, params).data["results"]}

    # Quien trabaja en todas las fincas también trabaja en esta.
    assert ids(farm=str(farm.pk)) == {str(here.pk), str(everywhere.pk)}
    # A todo empleado sin alcance, tenga o no permisos de campo; no al Productor ni a «todas».
    assert ids(without_farm="true") == {str(pending.pk), str(office.pk)}
    assert str(pending.pk) not in ids(without_farm="false")


def test_an_employee_of_a_farm_sees_only_the_accounts_of_its_farm(
    auth_client, owner, farm, other_farm
):
    viewer = make_delegate(owner.producer, ["accounts.users_view"], farm=farm)
    colleague = make_foreman(owner.producer, farm)
    elsewhere = make_foreman(owner.producer, other_farm)
    client = auth_client(viewer)

    listed = {row["id"] for row in client.get(USERS_URL).data["results"]}

    assert listed == {str(viewer.pk), str(colleague.pk)}
    assert client.get(user_url(elsewhere)).status_code == 404


def test_the_account_list_does_not_grow_its_queries_with_the_accounts(
    auth_client, owner, farm, django_assert_max_num_queries
):
    client = auth_client(owner)
    client.get(USERS_URL)
    for _ in range(6):
        make_foreman(owner.producer, farm)

    with django_assert_max_num_queries(13):
        response = client.get(USERS_URL)

    assert response.data["count"] == 7


# --- La sesión ---


def test_the_session_tells_the_farm_of_an_employee(auth_client, owner, farm):
    employee = make_foreman(owner.producer, farm)

    user = auth_client(employee).get("/api/auth/me").data["user"]

    assert user["farms"] == [{"id": str(farm.pk), "name": "La Esperanza", "is_active": True}]
    assert user["all_farms"] is False


def test_the_session_of_the_producer_reaches_all_its_farms(auth_client, owner):
    user = auth_client(owner).get("/api/auth/me").data["user"]

    assert user["farms"] == []
    assert user["all_farms"] is True


def test_the_association_reaches_no_farm_of_its_own(auth_client):
    user = auth_client(make_administrator()).get("/api/auth/me").data["user"]

    assert (user["farms"], user["all_farms"]) == ([], False)


def test_the_profile_shows_the_farm(auth_client, owner, farm):
    employee = make_foreman(owner.producer, farm)

    assert (
        auth_client(employee).get("/api/auth/profile").data["farms"][0]["name"] == "La Esperanza"
    )


# --- Cambiar de finca con labores pendientes ---


def labor(employee, farm, days_from_today):
    return AgriculturalActivityFactory(
        plot=PlotFactory(farm=farm),
        assignee=employee,
        scheduled_date=today_in_bogota() + timedelta(days=days_from_today),
    )


def test_an_employee_with_labors_to_do_is_not_moved(auth_client, owner, farm, other_farm):
    employee = make_foreman(owner.producer, farm)
    labor(employee, farm, 5)  # programada
    labor(employee, farm, -1)  # retrasada: todavía se reasigna

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "account_has_pending_work"
    assert (response.data["pending"], response.data["overdue"]) == (2, 0)
    assert "farm_ids" in response.data["fields"]
    employee.refresh_from_db()
    assert list(employee.farms.all()) == [farm]


def test_overdue_labors_do_not_keep_an_employee_in_its_farm(auth_client, owner, farm, other_farm):
    # Una vencida ya no se reasigna: bloquear por ella dejaría a la persona atada a la finca.
    employee = make_foreman(owner.producer, farm)
    labor(employee, farm, -10)

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json"
    )

    assert response.status_code == 200
    assert [farm["id"] for farm in response.data["farms"]] == [str(other_farm.pk)]


def test_the_message_mentions_the_overdue_ones_that_stay(auth_client, owner, farm, other_farm):
    employee = make_foreman(owner.producer, farm)
    labor(employee, farm, 3)
    labor(employee, farm, -10)

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json"
    )

    assert (response.data["pending"], response.data["overdue"]) == (1, 1)
    assert "vencidas (1)" in response.data["fields"]["farm_ids"][0]


def test_labors_done_or_in_other_farms_do_not_count(auth_client, owner, farm, other_farm):
    employee = make_foreman(owner.producer, farm)
    done_activity(plot=PlotFactory(farm=farm), assignee=employee)
    labor(employee, other_farm, 5)

    response = auth_client(owner).patch(
        user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json"
    )

    assert response.status_code == 200


# --- Varias fincas ---


def test_an_employee_works_in_several_farms_of_the_producer(auth_client, owner, farm, other_farm):
    role = RoleFactory(producer=owner.producer, permissions=["plots.view_plot"])
    response = auth_client(owner).post(
        USERS_URL,
        employee_body(role, farm_ids=[str(farm.pk), str(other_farm.pk)]),
        format="json",
    )

    assert response.status_code == 201
    assert {row["name"] for row in response.data["farms"]} == {"La Esperanza", "El Recreo"}


def test_adding_a_farm_does_not_wait_for_the_labors_of_the_others(
    auth_client, owner, farm, other_farm
):
    role = RoleFactory(producer=owner.producer, permissions=["plots.view_plot"])
    employee = grant_role(UserFactory(producer=owner.producer, farm=farm), role)
    labor(employee, farm, 5)

    response = auth_client(owner).patch(
        user_url(employee),
        {"farm_ids": [str(farm.pk), str(other_farm.pk)]},
        format="json",
    )

    assert response.status_code == 200
    assert len(response.data["farms"]) == 2


def test_removing_a_farm_waits_only_for_the_labors_in_that_farm(
    auth_client, owner, farm, other_farm
):
    employee = UserFactory(producer=owner.producer, farms=[farm, other_farm])
    grant_role(employee, get_system_role(FOREMAN))
    labor(employee, other_farm, 5)
    client = auth_client(owner)

    blocked = client.patch(user_url(employee), {"farm_ids": [str(farm.pk)]}, format="json")
    allowed = client.patch(user_url(employee), {"farm_ids": [str(other_farm.pk)]}, format="json")

    assert (blocked.status_code, blocked.data["pending"]) == (409, 1)
    assert allowed.status_code == 200
    assert [row["id"] for row in allowed.data["farms"]] == [str(other_farm.pk)]


def test_a_trusted_employee_of_several_farms_says_which_one(
    auth_client, producer, farm, other_farm
):
    trusted = make_delegate(producer, TRUSTED, farms=[farm, other_farm])
    field_role = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    client = auth_client(trusted)

    unsaid = client.post(USERS_URL, employee_body(field_role), format="json")
    said = client.post(
        USERS_URL,
        employee_body(field_role, email="otra@example.com", farm_ids=[str(other_farm.pk)]),
        format="json",
    )

    assert unsaid.status_code == 400
    assert "farm_ids" in unsaid.data["fields"]
    assert said.status_code == 201
    assert [row["id"] for row in said.data["farms"]] == [str(other_farm.pk)]


def test_an_employee_of_several_farms_sees_the_people_of_all_of_them(
    auth_client, owner, farm, other_farm
):
    third = FarmFactory(producer=owner.producer)
    viewer = make_delegate(owner.producer, ["accounts.users_view"], farms=[farm, other_farm])
    here = make_foreman(owner.producer, farm)
    there = make_foreman(owner.producer, other_farm)
    make_foreman(owner.producer, third)

    listed = {row["id"] for row in auth_client(viewer).get(USERS_URL).data["results"]}

    assert listed == {str(viewer.pk), str(here.pk), str(there.pk)}
