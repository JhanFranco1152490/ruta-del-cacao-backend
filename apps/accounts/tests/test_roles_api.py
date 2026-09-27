import pytest
from rest_framework.test import APIClient

from apps.accounts.models import AccountManagementEvent, Role
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, PRODUCER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.roles import (
    enable_association_access,
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

ROLES_URL = "/api/roles"
PERMISSIONS_URL = "/api/permissions"


def role_url(role) -> str:
    return f"{ROLES_URL}/{role.pk}"


# --- Acceso -----------------------------------------------------------------------------------


def test_list_requires_authentication():
    assert APIClient().get(ROLES_URL).status_code == 401


def test_list_requires_roles_view_permission(auth_client):
    response = auth_client(UserFactory()).get(ROLES_URL)

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_create_requires_roles_manage_permission(auth_client):
    producer = ProducerFactory()
    viewer = make_delegate(producer, ["accounts.roles_view"])

    response = auth_client(viewer).post(
        ROLES_URL, {"name": "Rol nuevo", "permission_codes": []}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


# --- Listar y consultar -------------------------------------------------------------------------


def test_a_producer_sees_system_roles_and_its_own_custom_roles(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    own_role = RoleFactory(producer=producer)
    RoleFactory()  # de otro productor

    response = auth_client(owner).get(ROLES_URL)

    assert response.status_code == 200
    codes = {item["id"] for item in response.data["results"]}
    assert str(own_role.id) in codes
    assert str(get_system_role(ADMINISTRATOR).id) in codes


def test_retrieving_a_role_from_another_producer_is_not_found(auth_client):
    owner = make_producer_owner(ProducerFactory())
    other_role = RoleFactory()

    response = auth_client(owner).get(role_url(other_role))

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_administrator_only_sees_custom_roles_with_association_access(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    role = RoleFactory(producer=producer)

    hidden = auth_client(admin).get(role_url(role))
    assert hidden.status_code == 404

    enable_association_access(producer)
    shown = auth_client(admin).get(role_url(role))
    assert shown.status_code == 200


def test_list_is_paginated(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).get(ROLES_URL)

    assert set(response.data) == {"count", "next", "previous", "results"}


# --- Crear ---------------------------------------------------------------------------------------


def test_a_producer_creates_a_custom_role_with_permissions_it_holds(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    response = auth_client(owner).post(
        ROLES_URL,
        {
            "name": "Administrador de finca",
            "description": "Gestiona cuentas y roles de la finca",
            "permission_codes": ["accounts.users_view", "accounts.users_create"],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["kind"] == Role.Kind.CUSTOM
    assert str(response.data["producer_id"]) == str(producer.id)
    assert sorted(response.data["permissions"]) == ["accounts.users_create", "accounts.users_view"]
    role = Role.objects.get(pk=response.data["id"])
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ROLE_CREATED,
        actor=owner,
        target_role_id=role.id,
    ).exists()


def test_a_non_administrator_cannot_send_producer_id(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "X", "permission_codes": [], "producer_id": str(ProducerFactory().id)},
        format="json",
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_administrator_must_send_producer_id(auth_client):
    admin = make_administrator()

    response = auth_client(admin).post(
        ROLES_URL, {"name": "X", "permission_codes": []}, format="json"
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_administrator_needs_association_access_to_create_for_a_producer(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()

    denied = auth_client(admin).post(
        ROLES_URL,
        {"name": "X", "permission_codes": [], "producer_id": str(producer.id)},
        format="json",
    )
    assert denied.status_code == 403
    assert denied.data["code"] == "exceeds_own_permissions"

    enable_association_access(producer)
    allowed = auth_client(admin).post(
        ROLES_URL,
        {"name": "Y", "permission_codes": [], "producer_id": str(producer.id)},
        format="json",
    )
    assert allowed.status_code == 201


def test_cannot_grant_a_permission_the_actor_lacks(auth_client):
    # El delegado necesita roles_manage para llegar siquiera al endpoint; lo que se prueba es
    # que no puede conceder un permiso *distinto* que tampoco tiene (users_create).
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.roles_manage", "accounts.users_view"])

    response = auth_client(delegate).post(
        ROLES_URL,
        {"name": "X", "permission_codes": ["accounts.users_create"]},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"
    assert "permission_codes" in response.data["fields"]


def test_cannot_grant_a_non_delegable_permission_even_if_the_actor_has_it(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    enable_association_access(producer)

    response = auth_client(admin).post(
        ROLES_URL,
        {"name": "X", "permission_codes": ["producers.view"], "producer_id": str(producer.id)},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_unknown_permission_code_is_a_validation_error(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "X", "permission_codes": ["accounts.no_existe"]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "permission_codes" in response.data["fields"]


def test_duplicate_name_against_a_system_role_is_rejected(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL, {"name": "administrador", "permission_codes": []}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_role_name"


def test_duplicate_name_within_the_same_producer_is_rejected(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    RoleFactory(producer=producer, name="Capataz de confianza")

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "capataz de confianza", "permission_codes": []},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_role_name"


def test_the_same_name_is_allowed_across_different_producers(auth_client):
    RoleFactory(name="Repetible")
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL, {"name": "Repetible", "permission_codes": []}, format="json"
    )

    assert response.status_code == 201


def test_unknown_field_is_rejected(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "X", "permission_codes": [], "code": "custom-code"},
        format="json",
    )

    assert response.status_code == 400
    assert "code" in response.data["fields"]


# --- Editar --------------------------------------------------------------------------------------


def test_a_producer_edits_its_own_role(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer, permissions=["accounts.users_view"])

    response = auth_client(owner).patch(
        role_url(role),
        {"name": "Nuevo nombre", "permission_codes": ["accounts.users_view"]},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == "Nuevo nombre"
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ROLE_UPDATED, target_role_id=role.id
    ).exists()


def test_editing_a_system_role_is_immutable(auth_client):
    admin = make_administrator()

    response = auth_client(admin).patch(
        f"{ROLES_URL}/{get_system_role(ADMINISTRATOR).id}", {"name": "Otro"}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "role_immutable"


def test_a_delegate_cannot_edit_a_role_with_permissions_it_lacks(auth_client):
    # roles_manage deja al delegado llegar al endpoint; el rol que intenta editar lleva un
    # permiso que el delegado no tiene (users_change_status), y por eso queda fuera de alcance.
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.roles_manage", "accounts.users_view"])
    stronger_role = RoleFactory(producer=producer, permissions=["accounts.users_change_status"])

    response = auth_client(delegate).patch(
        role_url(stronger_role), {"name": "Intento"}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_update_requires_at_least_one_field(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer)

    response = auth_client(owner).patch(role_url(role), {}, format="json")

    assert response.status_code == 400


def test_renaming_to_a_duplicate_name_is_rejected(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    RoleFactory(producer=producer, name="Ya existe")
    role = RoleFactory(producer=producer, name="Original")

    response = auth_client(owner).patch(role_url(role), {"name": "ya existe"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_role_name"


def test_renaming_to_its_own_name_is_not_a_duplicate(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer, name="Mismo nombre")

    response = auth_client(owner).patch(
        role_url(role), {"description": "Actualizado"}, format="json"
    )

    assert response.status_code == 200


# --- Borrar --------------------------------------------------------------------------------------


def test_a_producer_deletes_its_own_unused_role(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer)

    response = auth_client(owner).delete(role_url(role))

    assert response.status_code == 204
    assert not Role.objects.filter(pk=role.pk).exists()
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ROLE_DELETED, target_role_id=role.id
    ).exists()


def test_deleting_a_role_with_an_assigned_user_is_rejected(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer)
    grant_role(UserFactory(producer=producer), role)

    response = auth_client(owner).delete(role_url(role))

    assert response.status_code == 409
    assert response.data["code"] == "role_in_use"
    assert Role.objects.filter(pk=role.pk).exists()


def test_deleting_a_predefined_role_is_immutable(auth_client):
    admin = make_administrator()

    response = auth_client(admin).delete(f"{ROLES_URL}/{get_system_role(FOREMAN).id}")

    assert response.status_code == 403
    assert response.data["code"] == "role_immutable"


def test_a_producer_cannot_delete_another_producers_role(auth_client):
    owner = make_producer_owner(ProducerFactory())
    other_role = RoleFactory()

    response = auth_client(owner).delete(role_url(other_role))

    assert response.status_code == 404


# --- Catálogo de permisos ------------------------------------------------------------------------


def test_permission_catalog_requires_authentication():
    assert APIClient().get(PERMISSIONS_URL).status_code == 401


def test_permission_catalog_requires_roles_view_permission(auth_client):
    response = auth_client(UserFactory()).get(PERMISSIONS_URL)

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_permission_catalog_marks_grantable_for_a_delegate(auth_client):
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.roles_view", "accounts.users_view"])

    response = auth_client(delegate).get(PERMISSIONS_URL)

    by_code = {item["code"]: item for item in response.data["results"]}
    assert response.status_code == 200
    assert by_code["accounts.users_view"]["grantable"] is True
    assert by_code["accounts.roles_manage"]["grantable"] is False
    assert by_code["producers.view"]["grantable"] is False
    assert by_code["producers.view"]["delegable"] is False


def test_permission_catalog_marks_administrators_non_delegable_permissions_as_not_grantable(
    auth_client,
):
    admin = make_administrator()

    response = auth_client(admin).get(PERMISSIONS_URL)

    by_code = {item["code"]: item for item in response.data["results"]}
    assert by_code["producers.view"]["grantable"] is False
    assert by_code["accounts.association_access_manage"]["grantable"] is False
    assert by_code["accounts.users_view"]["grantable"] is True


def test_permission_catalog_is_sorted_by_code(auth_client):
    admin = make_administrator()

    response = auth_client(admin).get(PERMISSIONS_URL)

    codes = [item["code"] for item in response.data["results"]]
    assert codes == sorted(codes)


def test_producer_holding_the_role_code_matches_the_role_it_was_assigned():
    # Documenta el supuesto que usa acts_for_producer/is_association_admin: el rol Productor
    # identifica a la cuenta dueña, sin depender de un campo aparte.
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    assert owner.groups.filter(role__code=PRODUCER).exists()
