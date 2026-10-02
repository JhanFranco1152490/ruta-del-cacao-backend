import pytest

from apps.accounts.system_roles import PRODUCER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_administrator
from apps.producers.tests.factories import ProducerFactory

PROFILE_URL = "/api/auth/profile"
PROFILE_FIELDS = {
    "email",
    "first_name",
    "last_name",
    "document_type",
    "identity_document",
    "phone",
    "producer",
}

pytestmark = pytest.mark.django_db


def test_profile_of_a_producer_account_names_its_producer(auth_client):
    producer = ProducerFactory(first_name="Ana", last_name="Ejemplo")
    owner = grant_role(
        UserFactory(
            producer=producer,
            first_name="Luis",
            last_name="Pérez",
            identity_document="1094000111",
            phone="3001234567",
        ),
        get_system_role(PRODUCER),
    )

    response = auth_client(owner).get(PROFILE_URL)

    assert response.status_code == 200
    assert response.data == {
        "email": owner.email,
        "first_name": "Luis",
        "last_name": "Pérez",
        "document_type": "CC",
        "identity_document": "1094000111",
        "phone": "3001234567",
        "producer": {
            "id": str(producer.id),
            "member_code": producer.member_code,
            "first_name": "Ana",
            "last_name": "Ejemplo",
        },
    }


def test_profile_of_an_association_account_has_no_producer(auth_client):
    administrator = make_administrator()

    response = auth_client(administrator).get(PROFILE_URL)

    assert response.status_code == 200
    assert response.data["producer"] is None


def test_profile_only_exposes_the_account_data(auth_client):
    response = auth_client(make_administrator()).get(PROFILE_URL)

    assert set(response.data) == PROFILE_FIELDS


def test_profile_without_session_is_not_authenticated(api_client):
    response = api_client.get(PROFILE_URL)

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"
