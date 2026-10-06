import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import AccountManagementEvent, Role
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, PRODUCER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import (
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


def test_administrator_does_not_see_the_custom_roles_of_a_producer(auth_client):
    admin = make_administrator()
    role = RoleFactory(producer=ProducerFactory())

    response = auth_client(admin).get(role_url(role))

    assert response.status_code == 404


def test_superuser_sees_the_custom_roles_of_any_producer(auth_client):
    superuser = UserFactory(is_superuser=True)
    role = RoleFactory(producer=ProducerFactory())

    response = auth_client(superuser).get(role_url(role))

    assert response.status_code == 200


def test_list_is_paginated(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).get(ROLES_URL)

    assert set(response.data) == {"count", "next", "previous", "results"}


# --- Filtros y búsqueda ---------------------------------------------------------------------


def test_filter_by_kind(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    custom = RoleFactory(producer=producer)

    response = auth_client(owner).get(f"{ROLES_URL}?kind=custom")

    ids = {item["id"] for item in response.data["results"]}
    assert str(custom.id) in ids
    assert str(get_system_role(ADMINISTRATOR).id) not in ids


def test_filter_by_producer(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    own_role = RoleFactory(producer=producer)
    other_role = RoleFactory()  # de otro productor, invisible para este actor de todas formas

    response = auth_client(owner).get(f"{ROLES_URL}?producer={producer.id}")

    ids = {item["id"] for item in response.data["results"]}
    assert str(own_role.id) in ids
    assert str(other_role.id) not in ids


def test_search_ignores_accents_and_case(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    match = RoleFactory(producer=producer, name="Añíl")
    other = RoleFactory(producer=producer, name="Otro")

    response = auth_client(owner).get(f"{ROLES_URL}?search=anil")

    ids = {item["id"] for item in response.data["results"]}
    assert str(match.id) in ids
    assert str(other.id) not in ids


def test_ordering_descending_by_name(auth_client):
    # El orden por defecto ya es por nombre ascendente (`Role.Meta.ordering`): se pide
    # descendente para distinguir que el parámetro sí se está aplicando.
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    RoleFactory(producer=producer, name="Zeta")
    RoleFactory(producer=producer, name="Alfa")

    response = auth_client(owner).get(f"{ROLES_URL}?ordering=-name")

    names = [item["name"] for item in response.data["results"]]
    assert names == sorted(names, reverse=True)


def test_an_unknown_ordering_field_is_ignored(auth_client):
    owner = make_producer_owner(ProducerFactory())

    with_param = auth_client(owner).get(f"{ROLES_URL}?ordering=not_a_field")
    without_param = auth_client(owner).get(ROLES_URL)

    assert with_param.status_code == 200
    assert [item["id"] for item in with_param.data["results"]] == [
        item["id"] for item in without_param.data["results"]
    ]


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
    assert response.data["producer"] == {
        "id": str(producer.id),
        "member_code": producer.member_code,
        "first_name": producer.first_name,
        "last_name": producer.last_name,
    }
    assert sorted(response.data["permissions"]) == ["accounts.users_create", "accounts.users_view"]
    role = Role.objects.get(pk=response.data["id"])
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ROLE_CREATED,
        actor=owner,
        target_role_id=role.id,
    ).exists()


def test_creating_a_role_auto_includes_the_view_a_management_permission_needs(auth_client):
    # roles_manage sin roles_view deja a quien lo tiene sin cómo consultar lo que gestiona.
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "Solo gestiona roles", "permission_codes": ["accounts.roles_manage"]},
        format="json",
    )

    assert response.status_code == 201
    assert set(response.data["permissions"]) == {"accounts.roles_manage", "accounts.roles_view"}


def test_updating_a_role_auto_includes_the_view_a_management_permission_needs(auth_client):
    owner = make_producer_owner(ProducerFactory())
    role = RoleFactory(kind=Role.Kind.CUSTOM, producer=owner.producer)

    response = auth_client(owner).patch(
        role_url(role),
        {"permission_codes": ["accounts.users_update"]},
        format="json",
    )

    assert response.status_code == 200
    assert set(response.data["permissions"]) == {"accounts.users_update", "accounts.users_view"}


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


def test_administrator_cannot_create_a_role_for_a_producer(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()

    response = auth_client(admin).post(
        ROLES_URL,
        {"name": "X", "permission_codes": [], "producer_id": str(producer.id)},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_superuser_creates_a_role_for_any_producer(auth_client):
    superuser = UserFactory(is_superuser=True)
    producer = ProducerFactory()

    response = auth_client(superuser).post(
        ROLES_URL,
        {"name": "Y", "permission_codes": [], "producer_id": str(producer.id)},
        format="json",
    )

    assert response.status_code == 201


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


def test_a_producer_cannot_grant_a_non_delegable_permission(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "X", "permission_codes": ["producers.view"]},
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


def test_editing_your_own_role_cannot_remove_your_last_roles_manage(auth_client):
    producer = ProducerFactory()
    role = RoleFactory(
        producer=producer, permissions=["accounts.roles_view", "accounts.roles_manage"]
    )
    delegate = grant_role(UserFactory(producer=producer), role)

    response = auth_client(delegate).patch(
        role_url(role), {"permission_codes": ["accounts.roles_view"]}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "self_role_lockout"
    assert set(Role.objects.get(pk=role.pk).permission_codes) == {
        "accounts.roles_view",
        "accounts.roles_manage",
    }


def test_editing_your_own_role_is_allowed_if_another_role_still_covers_it(auth_client):
    producer = ProducerFactory()
    role = RoleFactory(
        producer=producer, permissions=["accounts.roles_view", "accounts.roles_manage"]
    )
    backup_role = RoleFactory(
        producer=producer, permissions=["accounts.roles_view", "accounts.roles_manage"]
    )
    delegate = grant_role(grant_role(UserFactory(producer=producer), role), backup_role)

    response = auth_client(delegate).patch(
        role_url(role), {"permission_codes": ["accounts.roles_view"]}, format="json"
    )

    assert response.status_code == 200
    assert set(response.data["permissions"]) == {"accounts.roles_view"}


def test_editing_your_own_role_without_touching_roles_manage_is_allowed(auth_client):
    producer = ProducerFactory()
    role = RoleFactory(
        producer=producer, permissions=["accounts.roles_view", "accounts.roles_manage"]
    )
    delegate = grant_role(UserFactory(producer=producer), role)

    response = auth_client(delegate).patch(role_url(role), {"name": "Renombrado"}, format="json")

    assert response.status_code == 200


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


def test_permission_catalog_excludes_permissions_no_custom_role_can_ever_hold(auth_client):
    # Un rol propio siempre está atado a un productor: producers.* nunca se le puede asignar,
    # para nadie, así que no tiene sentido ofrecerlo como opción aunque quien consulta el
    # catálogo sea Administrador (con `producers.*` en su propio rol de sistema) o superusuario.
    admin = make_administrator()

    response = auth_client(admin).get(PERMISSIONS_URL)

    codes = {item["code"] for item in response.data["results"]}
    assert "producers.view" not in codes
    assert "accounts.users_view" in codes


def test_permission_catalog_marks_what_each_permission_requires(auth_client):
    # El frontend usa esto para marcar solo, antes de guardar, el permiso de vista que un
    # permiso de acción necesita (ver with_dependencies en registry.py): sin esto, se entera
    # de la dependencia recién en la respuesta de crear/editar el rol.
    admin = make_administrator()

    response = auth_client(admin).get(PERMISSIONS_URL)

    by_code = {item["code"]: item for item in response.data["results"]}
    assert by_code["accounts.roles_manage"]["requires"] == "accounts.roles_view"
    assert by_code["accounts.users_create"]["requires"] == "accounts.users_view"
    assert by_code["accounts.users_view"]["requires"] is None


def test_permission_catalog_offers_characterizing_plots_but_not_the_variety_catalog(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).get(PERMISSIONS_URL)

    by_code = {item["code"]: item for item in response.data["results"]}
    characterize = by_code["crops.change_plotcharacterization"]
    assert characterize["area"] == "crops"
    assert characterize["requires"] == "plots.view_plot"
    assert characterize["grantable"] is True
    assert "crops.manage_cacaovariety" not in by_code


def test_a_custom_role_that_characterizes_plots_can_also_see_them(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "Caracterizador", "permission_codes": ["crops.change_plotcharacterization"]},
        format="json",
    )

    assert response.status_code == 201
    assert sorted(response.data["permissions"]) == [
        "crops.change_plotcharacterization",
        "farms.view_farm",
        "plots.view_plot",
    ]


def test_a_producer_cannot_delegate_the_variety_catalog(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        ROLES_URL,
        {"name": "Catálogo", "permission_codes": ["crops.manage_cacaovariety"]},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


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


# --- Nombres de los permisos de cada rol --------------------------------------------------------


def test_a_role_brings_the_name_of_each_permission_even_if_it_is_not_delegable(auth_client):
    # Los permisos no delegables no están en el catálogo de /api/permissions (que solo alimenta
    # el formulario de roles propios), pero el detalle de un rol del sistema debe poder nombrarlos.
    admin = make_administrator()

    response = auth_client(admin).get(role_url(get_system_role(ADMINISTRATOR)))

    details = {item["code"]: item["name"] for item in response.data["permission_details"]}
    assert details["producers.view"] == "Puede consultar productores"
    assert set(details) == set(response.data["permissions"])


def test_the_permission_details_follow_the_order_of_the_permission_codes(auth_client):
    admin = make_administrator()

    response = auth_client(admin).get(role_url(get_system_role(PRODUCER)))

    assert [item["code"] for item in response.data["permission_details"]] == response.data[
        "permissions"
    ]


def test_the_list_takes_the_same_queries_with_one_or_many_roles(auth_client):
    superuser = UserFactory(is_superuser=True)
    client = auth_client(superuser)
    with CaptureQueriesContext(connection) as one:
        client.get(ROLES_URL)

    producer = ProducerFactory()
    for _ in range(5):
        RoleFactory(
            producer=producer, permissions=["accounts.users_view", "accounts.users_create"]
        )
    with CaptureQueriesContext(connection) as many:
        response = client.get(ROLES_URL)

    assert len(response.data["results"]) > 5
    assert len(many) == len(one)


def test_roles_can_be_ordered_by_producer_with_the_system_roles_first(auth_client):
    superuser = UserFactory(is_superuser=True)
    later = RoleFactory(producer=ProducerFactory(member_code="PROD-000002"), name="Beta")
    earlier = RoleFactory(producer=ProducerFactory(member_code="PROD-000001"), name="Alfa")

    response = auth_client(superuser).get(f"{ROLES_URL}?ordering=producer&page_size=100")

    results = response.data["results"]
    assert all(item["producer"] is None for item in results[:-2])
    assert [item["id"] for item in results[-2:]] == [str(earlier.id), str(later.id)]


def test_a_producer_can_be_asked_for_together_with_the_system_roles(auth_client):
    superuser = UserFactory(is_superuser=True)
    chosen, other = ProducerFactory(), ProducerFactory()
    own = RoleFactory(producer=chosen, name="Propio")
    foreign = RoleFactory(producer=other, name="Ajeno")

    response = auth_client(superuser).get(
        f"{ROLES_URL}?producer={chosen.id}&include_system=true&page_size=100"
    )

    ids = {item["id"] for item in response.data["results"]}
    codes = {item["code"] for item in response.data["results"] if item["code"]}
    assert str(own.id) in ids
    assert str(foreign.id) not in ids
    assert {ADMINISTRATOR, PRODUCER} <= codes


def test_filtering_by_producer_alone_still_leaves_the_system_roles_out(auth_client):
    superuser = UserFactory(is_superuser=True)
    chosen = ProducerFactory()
    own = RoleFactory(producer=chosen)

    response = auth_client(superuser).get(f"{ROLES_URL}?producer={chosen.id}&page_size=100")

    assert [item["id"] for item in response.data["results"]] == [str(own.id)]


def test_the_system_roles_flag_alone_changes_nothing(auth_client):
    superuser = UserFactory(is_superuser=True)
    RoleFactory(producer=ProducerFactory())

    plain = auth_client(superuser).get(f"{ROLES_URL}?page_size=100")
    flagged = auth_client(superuser).get(f"{ROLES_URL}?include_system=true&page_size=100")

    assert plain.data["count"] == flagged.data["count"]
