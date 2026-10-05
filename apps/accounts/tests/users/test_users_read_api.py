import pytest
from rest_framework.test import APIClient

from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory, make_pending_user
from apps.accounts.tests.role_helpers import grant_role, make_administrator, make_producer_owner
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

USERS_URL = "/api/users"


def user_url(user) -> str:
    return f"{USERS_URL}/{user.pk}"


# --- Acceso -------------------------------------------------------------------------------------


def test_list_requires_authentication():
    assert APIClient().get(USERS_URL).status_code == 401


def test_list_requires_users_view_permission(auth_client):
    assert auth_client(UserFactory()).get(USERS_URL).status_code == 403


def test_retrieve_requires_users_view_permission(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(UserFactory()).get(user_url(owner))

    assert response.status_code == 403


# --- Alcance -------------------------------------------------------------------------------------


def test_a_producer_only_sees_its_own_accounts(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    other_owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).get(USERS_URL)

    ids = {item["id"] for item in response.data["results"]}
    assert {str(owner.id), str(employee.id)} <= ids
    assert str(other_owner.id) not in ids


def test_administrator_sees_the_producer_account_but_not_its_employees(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    assert auth_client(admin).get(user_url(employee)).status_code == 404
    assert auth_client(admin).get(user_url(owner)).status_code == 200


def test_superuser_sees_the_employees_of_any_producer(auth_client):
    superuser = UserFactory(is_superuser=True)
    employee = UserFactory(producer=ProducerFactory())

    assert auth_client(superuser).get(user_url(employee)).status_code == 200


def test_superuser_never_appears(auth_client):
    admin = make_administrator()
    superuser = UserFactory(is_superuser=True)

    list_response = auth_client(admin).get(USERS_URL)
    ids = {item["id"] for item in list_response.data["results"]}
    assert str(superuser.id) not in ids
    assert auth_client(admin).get(user_url(superuser)).status_code == 404
    # Ni siquiera para otro superusuario.
    other_superuser = UserFactory(is_superuser=True)
    assert auth_client(other_superuser).get(user_url(superuser)).status_code == 404


def test_account_without_producer_or_administrator_role_sees_an_empty_list(auth_client):
    stray = UserFactory(permissions=["accounts.users_view"])
    UserFactory(producer=ProducerFactory())

    response = auth_client(stray).get(USERS_URL)

    assert response.status_code == 200
    assert response.data["results"] == []


def test_retrieving_another_producers_account_is_not_found(auth_client):
    owner = make_producer_owner(ProducerFactory())
    other_employee = UserFactory(producer=ProducerFactory())

    response = auth_client(owner).get(user_url(other_employee))

    assert response.status_code == 404


# --- Filtros y búsqueda -------------------------------------------------------------------------


def test_filter_by_status(auth_client):
    admin = make_administrator()
    active = make_producer_owner(ProducerFactory())
    inactive = make_producer_owner(ProducerFactory())
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    response = auth_client(admin).get(f"{USERS_URL}?status=inactive")

    ids = {item["id"] for item in response.data["results"]}
    assert str(inactive.id) in ids
    assert str(active.id) not in ids


def test_filter_by_activation_pending(auth_client):
    admin = make_administrator()
    pending = grant_role(make_pending_user(), get_system_role(ADMINISTRATOR))
    active = make_administrator()

    response = auth_client(admin).get(f"{USERS_URL}?activation_pending=true")

    ids = {item["id"] for item in response.data["results"]}
    assert str(pending.id) in ids
    assert str(active.id) not in ids


def test_filter_by_role(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreman_role = get_system_role(FOREMAN)
    employee = grant_role(UserFactory(producer=producer), foreman_role)
    other_employee = UserFactory(producer=producer)

    response = auth_client(owner).get(f"{USERS_URL}?role={foreman_role.id}")

    ids = {item["id"] for item in response.data["results"]}
    assert str(employee.id) in ids
    assert str(other_employee.id) not in ids


def test_filter_by_producer_only_for_administrator(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    admin = make_administrator()

    as_admin = auth_client(admin).get(f"{USERS_URL}?producer={producer.id}")
    assert as_admin.status_code == 200
    assert str(owner.id) in {item["id"] for item in as_admin.data["results"]}

    as_owner = auth_client(owner).get(f"{USERS_URL}?producer={producer.id}")
    assert as_owner.status_code == 400


def test_filter_by_municipality(auth_client):
    cucuta = ProducerFactory(municipality_code="54001")
    ocana = ProducerFactory(municipality_code="54498")
    owner_in_cucuta = make_producer_owner(cucuta)
    owner_in_ocana = make_producer_owner(ocana)
    admin = make_administrator()

    response = auth_client(admin).get(f"{USERS_URL}?municipality=54001")

    ids = {item["id"] for item in response.data["results"]}
    assert str(owner_in_cucuta.id) in ids
    assert str(owner_in_ocana.id) not in ids


def test_search_ignores_accents_and_case(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    match = UserFactory(producer=producer, first_name="José", last_name="Pérez")

    response = auth_client(owner).get(f"{USERS_URL}?search=jose perez")

    assert str(match.id) in {item["id"] for item in response.data["results"]}


def test_list_is_paginated(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).get(USERS_URL)

    assert set(response.data) == {"count", "next", "previous", "results"}


def test_ordering_by_email(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    UserFactory(producer=producer, email="zzz@example.com")
    UserFactory(producer=producer, email="aaa@example.com")

    response = auth_client(owner).get(f"{USERS_URL}?ordering=email")

    emails = [item["email"] for item in response.data["results"]]
    assert emails == sorted(emails)


def test_ordering_descending(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    UserFactory(producer=producer, email="zzz@example.com")
    UserFactory(producer=producer, email="aaa@example.com")

    response = auth_client(owner).get(f"{USERS_URL}?ordering=-email")

    emails = [item["email"] for item in response.data["results"]]
    assert emails == sorted(emails, reverse=True)


def test_an_unknown_ordering_field_is_ignored(auth_client):
    owner = make_producer_owner(ProducerFactory())
    UserFactory(producer=owner.producer)

    with_param = auth_client(owner).get(f"{USERS_URL}?ordering=not_a_field")
    without_param = auth_client(owner).get(USERS_URL)

    assert with_param.status_code == 200
    assert [item["id"] for item in with_param.data["results"]] == [
        item["id"] for item in without_param.data["results"]
    ]


# --- Representación --------------------------------------------------------------------------


def test_account_representation_shape(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = grant_role(
        UserFactory(producer=producer, phone="3001234567"), get_system_role(FOREMAN)
    )

    response = auth_client(owner).get(user_url(employee))

    assert response.status_code == 200
    body = response.data
    assert body["producer"]["id"] == str(producer.id)
    assert body["producer"]["member_code"] == producer.member_code
    assert body["producer"]["status"] == "active"
    assert body["producer"]["municipality_code"] == producer.municipality_code
    assert {role["code"] for role in body["roles"]} == {FOREMAN}
    assert body["status"] == "active"
    assert body["activation_pending"] is False
    assert body["created_at"] is not None


def test_administrator_account_has_a_null_producer(auth_client):
    admin = make_administrator()

    response = auth_client(admin).get(user_url(admin))

    assert response.data["producer"] is None
