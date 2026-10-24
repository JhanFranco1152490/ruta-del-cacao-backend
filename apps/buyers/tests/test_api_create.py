import pytest

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.buyers.models import Buyer
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory, buyer_data

pytestmark = pytest.mark.django_db

URL = "/api/buyers"
CONTACT_REQUIRED = ["Escribe un teléfono o un correo."]


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


def test_create_needs_a_session_and_the_permission(anonymous_client, auth_client, producer):
    viewer = make_delegate(producer, ["buyers.view_buyer"], all_farms=True)

    assert anonymous_client.post(URL, buyer_data(), format="json").status_code == 401
    assert auth_client(viewer).post(URL, buyer_data(), format="json").status_code == 403
    assert not Buyer.objects.exists()


def test_the_sales_manager_registers_buyers(auth_client, producer):
    manager = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)),
        get_system_role(SALES_MANAGER),
    )

    response = auth_client(manager).post(URL, buyer_data(), format="json")

    assert response.status_code == 201
    assert Buyer.objects.get().producer_id == producer.pk


def test_create_returns_201_with_location_and_the_buyer(auth_client, owner, producer):
    response = auth_client(owner).post(
        URL,
        buyer_data(contact_name="  Persona de Ejemplo ", email=" Compras@Example.COM ", phone=""),
        format="json",
    )

    assert response.status_code == 201
    created = Buyer.objects.get()
    assert response["Location"] == f"{URL}/{created.pk}"
    assert (response.data["version"], response.data["is_active"]) == (1, True)
    assert response.data["has_records"] is False
    assert response.data["producer"]["id"] == str(producer.pk)
    assert (created.contact_name, created.email, created.phone) == (
        "Persona de Ejemplo",
        "compras@example.com",
        None,
    )


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"name": None}, "name"),
        ({"name": " "}, "name"),
        ({"name": "x"}, "name"),
        ({"name": "x" * 121}, "name"),
        ({"document_type": None}, "document_type"),
        ({"document_type": "RUT"}, "document_type"),
        ({"identity_document": None}, "identity_document"),
        ({"identity_document": "12345"}, "identity_document"),
        ({"identity_document": "1" * 16}, "identity_document"),
        ({"identity_document": "900.123.456"}, "identity_document"),
        ({"buyer_type": None}, "buyer_type"),
        ({"buyer_type": "retail"}, "buyer_type"),
        ({"contact_name": "x"}, "contact_name"),
        ({"phone": "123456"}, "phone"),
        ({"phone": "12345678901"}, "phone"),
        ({"phone": "300-123-4567"}, "phone"),
        ({"email": "compras@"}, "email"),
        ({"phone": "", "email": ""}, "phone"),
        ({"phone": "", "email": ""}, "email"),
        ({"is_active": False}, "is_active"),
        ({"version": 3}, "version"),
        ({"producer_id": "6f1a7e0e-0000-4000-8000-000000000000"}, "producer_id"),
    ],
)
def test_create_rejects_invalid_data_by_field(auth_client, owner, changes, field):
    body = {**buyer_data(), **changes}
    body = {key: value for key, value in body.items() if value is not None}

    response = auth_client(owner).post(URL, body, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert field in response.data["fields"]
    assert not Buyer.objects.exists()


def test_without_phone_or_email_both_fields_say_why(auth_client, owner):
    body = {key: value for key, value in buyer_data().items() if key != "phone"}

    response = auth_client(owner).post(URL, body, format="json")

    assert response.data["fields"]["phone"] == CONTACT_REQUIRED
    assert response.data["fields"]["email"] == CONTACT_REQUIRED


def test_a_repeated_document_answers_409_with_the_existing_buyer(auth_client, owner, producer):
    existing = BuyerFactory(producer=producer, identity_document="900123456", is_active=False)

    response = auth_client(owner).post(URL, buyer_data(name="Otro nombre"), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"
    assert response.data["existing"] == {
        "id": str(existing.pk),
        "name": existing.name,
        "is_active": False,
    }
    assert "identity_document" in response.data["fields"]


def test_the_technical_account_creates_for_a_named_producer(auth_client, producer):
    client = auth_client(UserFactory(is_superuser=True))

    response = client.post(URL, buyer_data(producer_id=str(producer.pk)), format="json")

    assert response.status_code == 201
    assert response.data["producer"]["id"] == str(producer.pk)


def test_the_technical_account_must_name_the_producer(auth_client):
    response = auth_client(UserFactory(is_superuser=True)).post(URL, buyer_data(), format="json")

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]
