"""El alcance que admite cada rol y quién crea o cambia roles según las fincas que alcanza."""

import pytest

from apps.accounts.models import Role
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    SALES_MANAGER,
)
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

ROLES_URL = "/api/roles"
MANAGER = [
    "accounts.roles_view",
    "accounts.roles_manage",
    "accounts.users_view",
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
    return FarmFactory(producer=producer)


@pytest.fixture
def other_farm(producer):
    return FarmFactory(producer=producer)


def role_url(role) -> str:
    return f"{ROLES_URL}/{role.pk}"


def create(client, **overrides):
    data = {"name": "Rol nuevo", "permission_codes": ["plots.view_plot"], **overrides}
    return client.post(ROLES_URL, data, format="json")


# --- Qué dice cada rol ---


def test_the_system_roles_carry_their_scope(auth_client, owner):
    response = auth_client(owner).get(ROLES_URL)

    scopes = {row["code"]: row["farm_scope"] for row in response.data["results"] if row["code"]}
    assert scopes[FOREMAN] == "one"
    assert scopes[SALES_MANAGER] == scopes[QUALITY_MANAGER] == "many"
    # Productor y Administrador no llevan fincas.
    assert scopes[PRODUCER] is None
    assert scopes[ADMINISTRATOR] is None or ADMINISTRATOR not in scopes


def test_a_custom_role_takes_several_farms_unless_told_otherwise(auth_client, owner):
    default = create(auth_client(owner))
    asked = create(auth_client(owner), name="Otro", farm_scope="one")

    assert default.status_code == 201 and default.data["farm_scope"] == "many"
    assert asked.status_code == 201 and asked.data["farm_scope"] == "one"


def test_an_unknown_scope_is_not_accepted(auth_client, owner):
    response = create(auth_client(owner), farm_scope="some")

    assert response.status_code == 400
    assert "farm_scope" in response.data["fields"]


# --- Quién da el alcance de un rol ---


def test_only_who_reaches_all_the_farms_creates_an_all_farms_role(auth_client, producer, farm):
    limited = make_delegate(producer, MANAGER, farm=farm)
    everywhere = make_delegate(producer, MANAGER, all_farms=True)

    denied = create(auth_client(limited), farm_scope="all")
    allowed = create(auth_client(everywhere), farm_scope="all")

    assert denied.status_code == 403
    assert allowed.status_code == 201


def test_a_limited_employee_creates_the_roles_of_its_people(auth_client, producer, farm):
    limited = make_delegate(producer, MANAGER, farm=farm)

    response = create(auth_client(limited), farm_scope="one")

    assert response.status_code == 201


# --- Cambiar el alcance de un rol ---


def test_changing_the_scope_is_rejected_when_accounts_would_not_fit(
    auth_client, owner, producer, farm, other_farm
):
    role = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    grant_role(UserFactory(producer=producer, farms=[farm, other_farm]), role)
    grant_role(UserFactory(producer=producer, farm=farm), role)
    client = auth_client(owner)

    to_one = client.patch(role_url(role), {"farm_scope": "one"}, format="json")
    to_all = client.patch(role_url(role), {"farm_scope": "all"}, format="json")

    assert (to_one.status_code, to_one.data["code"], to_one.data["accounts"]) == (
        409,
        "role_scope_in_use",
        1,
    )
    assert (to_all.status_code, to_all.data["accounts"]) == (409, 2)
    role.refresh_from_db()
    assert role.farm_scope == Role.FarmScope.MANY


def test_the_scope_changes_when_every_account_already_fits(auth_client, owner, producer, farm):
    role = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    grant_role(UserFactory(producer=producer, farm=farm), role)

    response = auth_client(owner).patch(role_url(role), {"farm_scope": "one"}, format="json")

    assert response.status_code == 200
    assert response.data["farm_scope"] == "one"


def test_a_role_without_accounts_changes_freely(auth_client, owner, producer):
    role = RoleFactory(producer=producer, permissions=["plots.view_plot"])

    response = auth_client(owner).patch(role_url(role), {"farm_scope": "all"}, format="json")

    assert response.status_code == 200


# --- Editar roles según las fincas que alcanza quien edita ---


def test_a_limited_employee_edits_a_role_only_its_own_people_have(auth_client, producer, farm):
    limited = make_delegate(producer, MANAGER, farm=farm)
    role = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    grant_role(UserFactory(producer=producer, farm=farm), role)

    response = auth_client(limited).patch(role_url(role), {"name": "Operario"}, format="json")

    assert response.status_code == 200


def test_a_limited_employee_does_not_edit_a_role_held_by_accounts_of_other_farms(
    auth_client, producer, farm, other_farm
):
    limited = make_delegate(producer, MANAGER, farm=farm)
    role = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    grant_role(UserFactory(producer=producer, farm=farm), role)
    grant_role(UserFactory(producer=producer, farm=other_farm), role)

    response = auth_client(limited).patch(role_url(role), {"name": "Operario"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "role_in_use_outside_scope"
    role.refresh_from_db()
    assert role.name != "Operario"


def test_who_reaches_all_the_farms_edits_any_role(auth_client, owner, producer, farm, other_farm):
    everywhere = make_delegate(producer, MANAGER, all_farms=True)
    role = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    grant_role(UserFactory(producer=producer, farm=other_farm), role)

    assert (
        auth_client(everywhere).patch(role_url(role), {"name": "A"}, format="json").status_code
        == 200
    )
    assert (
        auth_client(owner).patch(role_url(role), {"name": "B"}, format="json").status_code == 200
    )


def test_a_limited_employee_still_sees_every_role_of_the_producer(auth_client, producer, farm):
    limited = make_delegate(producer, MANAGER, farm=farm)
    hidden = RoleFactory(producer=producer, permissions=["plots.view_plot"])
    grant_role(UserFactory(producer=producer, farm=FarmFactory(producer=producer)), hidden)

    response = auth_client(limited).get(ROLES_URL)

    assert str(hidden.pk) in {row["id"] for row in response.data["results"]}
