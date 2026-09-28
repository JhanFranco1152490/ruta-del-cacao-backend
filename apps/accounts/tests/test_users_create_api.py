import smtplib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.db import connection
from django.test import override_settings

from apps.accounts.models import AccountManagementEvent, User
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, PRODUCER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.helpers import csrf_client, open_session
from apps.accounts.tests.roles import (
    enable_association_access,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

USERS_URL = "/api/users"


# --- Empleado --------------------------------------------------------------------------------


def test_a_producer_creates_an_employee_with_a_predefined_role(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreman = get_system_role(FOREMAN)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "empleado@example.com",
            "document_type": "CC",
            "identity_document": "12.345.678",
            "first_name": "Luis",
            "last_name": "Gómez",
            "role_ids": [str(foreman.id)],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["activation_email_sent"] is True
    assert response.data["identity_document"] == "12345678"
    user = User.objects.get(pk=response.data["id"])
    assert str(user.producer_id) == str(producer.id)
    assert user.groups.filter(role__code=FOREMAN).exists()
    assert not user.has_usable_password()
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ACCOUNT_CREATED, target_user=user, actor=owner
    ).exists()
    assert len(mail.outbox) == 1


def test_an_employee_created_by_a_non_administrator_cannot_send_producer_id(auth_client):
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_create"])
    foreman = get_system_role(FOREMAN)

    response = auth_client(delegate).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreman.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_administrator_must_send_producer_id_for_an_employee(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    enable_association_access(producer)
    foreman = get_system_role(FOREMAN)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreman.id)],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_administrator_creates_an_employee_when_association_access_is_enabled(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    enable_association_access(producer)
    foreman = get_system_role(FOREMAN)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreman.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 201


def test_administrator_needs_association_access_to_create_an_employee(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    foreman = get_system_role(FOREMAN)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreman.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_role_from_another_producer_is_a_validation_error(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreign_role = RoleFactory()

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreign_role.id)],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "role_ids" in response.data["fields"]


def test_role_ids_cannot_be_empty(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "role_ids" in response.data["fields"]


# --- Cuenta Productor --------------------------------------------------------------------------


def test_administrator_creates_the_producer_account_from_the_record(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    producer_role = get_system_role(PRODUCER)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "cuenta@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["document_type"] == producer.document_type
    assert response.data["identity_document"] == producer.identity_document
    assert response.data["first_name"] == producer.first_name
    assert response.data["last_name"] == producer.last_name


def test_producer_account_creation_rejects_personal_fields(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    producer_role = get_system_role(PRODUCER)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "cuenta@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(producer.id),
            "first_name": "No debería enviarse",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "first_name" in response.data["fields"]


def test_only_administrator_can_create_a_producer_account(auth_client):
    owner = make_producer_owner(ProducerFactory())
    other_producer = ProducerFactory()
    producer_role = get_system_role(PRODUCER)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(other_producer.id),
        },
        format="json",
    )

    assert response.status_code == 403


def test_producer_account_creation_rejects_an_inactive_producer(auth_client):
    admin = make_administrator()
    producer = ProducerFactory(status=Producer.Status.INACTIVE)
    producer_role = get_system_role(PRODUCER)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "cuenta@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "producer_inactive"


def test_producer_account_creation_rejects_a_producer_that_already_has_an_account(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    make_producer_owner(producer)
    producer_role = get_system_role(PRODUCER)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "otra@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "producer_already_linked"


def test_combining_the_producer_role_with_another_role_is_rejected(auth_client):
    admin = make_administrator()
    producer = ProducerFactory()
    producer_role = get_system_role(PRODUCER)
    foreman = get_system_role(FOREMAN)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "role_ids": [str(producer_role.id), str(foreman.id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_concurrent_producer_account_creation_only_succeeds_once(system_roles):
    producer = ProducerFactory()
    admin = make_administrator()
    producer_role = get_system_role(PRODUCER)
    clients = [open_session(csrf_client(), admin) for _ in range(2)]
    payloads = [
        {
            "email": "primera@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(producer.id),
        },
        {
            "email": "segunda@example.com",
            "role_ids": [str(producer_role.id)],
            "producer_id": str(producer.id),
        },
    ]
    barrier = Barrier(2)

    def attempt(pair):
        client, payload = pair
        try:
            barrier.wait()
            return client.post(USERS_URL, payload, format="json")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(attempt, zip(clients, payloads)))

    assert sorted(response.status_code for response in responses) == [201, 409]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.data["code"] == "producer_already_linked"
    assert User.objects.filter(producer=producer, groups__role__code=PRODUCER).count() == 1


# --- Administrador -----------------------------------------------------------------------------


def test_only_an_administrator_can_create_another_administrator(auth_client):
    owner = make_producer_owner(ProducerFactory())
    admin_role = get_system_role(ADMINISTRATOR)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "nuevo@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(admin_role.id)],
        },
        format="json",
    )

    assert response.status_code == 403


def test_an_administrator_creates_another_administrator(auth_client):
    admin = make_administrator()
    admin_role = get_system_role(ADMINISTRATOR)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "nuevo@example.com",
            "document_type": "CC",
            "identity_document": "7654321",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(admin_role.id)],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["producer"] is None


def test_administrator_account_creation_rejects_producer_id(auth_client):
    admin = make_administrator()
    admin_role = get_system_role(ADMINISTRATOR)

    response = auth_client(admin).post(
        USERS_URL,
        {
            "email": "nuevo@example.com",
            "document_type": "CC",
            "identity_document": "1112223",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(admin_role.id)],
            "producer_id": str(ProducerFactory().id),
        },
        format="json",
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


# --- Duplicados y campos no permitidos -----------------------------------------------------------


def test_duplicate_email_with_different_case_and_spaces_is_rejected(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    UserFactory(email="ana@example.com")
    foreman = get_system_role(FOREMAN)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": " Ana@Example.com ",
            "document_type": "CC",
            "identity_document": "9999999",
            "first_name": "Otra",
            "last_name": "Persona",
            "role_ids": [str(foreman.id)],
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_email"


def test_duplicate_document_is_rejected_without_identifiers(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    UserFactory(document_type="CC", identity_document="55555555")
    foreman = get_system_role(FOREMAN)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "nueva@example.com",
            "document_type": "CC",
            "identity_document": "555.555.55",
            "first_name": "X",
            "last_name": "Y",
            "role_ids": [str(foreman.id)],
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"
    assert "identity_document" in response.data["fields"]
    assert "existing_producer_id" not in response.data
    assert "existing_user_id" not in response.data


def test_is_superuser_in_the_body_is_rejected(auth_client):
    owner = make_producer_owner(ProducerFactory())
    foreman = get_system_role(FOREMAN)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreman.id)],
            "is_superuser": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "is_superuser" in response.data["fields"]


# --- Envío del correo de activación --------------------------------------------------------------


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        recipients = {address: (550, b"rechazado") for m in email_messages for address in m.to}
        raise smtplib.SMTPRecipientsRefused(recipients)


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "apps.accounts.tests.test_users_create_api.FailingEmailBackend",
            "OPTIONS": {},
        }
    }
)
def test_activation_email_failure_still_creates_the_account(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreman = get_system_role(FOREMAN)

    response = auth_client(owner).post(
        USERS_URL,
        {
            "email": "x@example.com",
            "document_type": "CC",
            "identity_document": "1234567",
            "first_name": "A",
            "last_name": "B",
            "role_ids": [str(foreman.id)],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["activation_email_sent"] is False
