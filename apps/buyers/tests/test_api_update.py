import pytest

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db

URL = "/api/buyers"
CONTACT_REQUIRED = ["Escribe un teléfono o un correo."]


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def buyer(producer):
    return BuyerFactory(producer=producer, name="Cacao Andino")


def detail(buyer) -> str:
    return f"{URL}/{buyer.pk}"


def test_update_needs_a_session_and_the_permission(anonymous_client, auth_client, producer, buyer):
    viewer = make_delegate(producer, ["buyers.view_buyer"], all_farms=True)
    body = {"name": "Otro", "expected_version": 1}

    assert anonymous_client.patch(detail(buyer), body, format="json").status_code == 401
    assert auth_client(viewer).patch(detail(buyer), body, format="json").status_code == 403


def test_the_sales_manager_edits_and_deactivates(auth_client, producer, buyer):
    manager = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)),
        get_system_role(SALES_MANAGER),
    )
    client = auth_client(manager)

    edited = client.patch(detail(buyer), {"name": "Otro", "expected_version": 1}, format="json")
    off = client.patch(detail(buyer), {"is_active": False, "expected_version": 2}, format="json")

    assert edited.status_code == 200
    assert (off.status_code, off.data["is_active"], off.data["version"]) == (200, False, 3)


def test_update_returns_the_buyer_with_the_new_version(auth_client, owner, buyer):
    response = auth_client(owner).patch(
        detail(buyer),
        {"email": " Ventas@Example.COM ", "contact_name": "", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    assert (response.data["email"], response.data["contact_name"]) == (
        "ventas@example.com",
        None,
    )
    assert response.data["version"] == 2


@pytest.mark.parametrize(
    "body, field",
    [
        ({"name": "Otro"}, "expected_version"),
        ({"name": "", "expected_version": 1}, "name"),
        ({"identity_document": "12345", "expected_version": 1}, "identity_document"),
        ({"buyer_type": "retail", "expected_version": 1}, "buyer_type"),
        ({"phone": None, "expected_version": 1}, "phone"),
        (
            {"producer_id": "6f1a7e0e-0000-4000-8000-000000000000", "expected_version": 1},
            "producer_id",
        ),
        ({"version": 4, "expected_version": 1}, "version"),
    ],
)
def test_update_rejects_invalid_data_by_field(auth_client, owner, buyer, body, field):
    response = auth_client(owner).patch(detail(buyer), body, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert field in response.data["fields"]
    buyer.refresh_from_db()
    assert (buyer.name, buyer.version) == ("Cacao Andino", 1)


def test_only_the_version_is_not_a_change(auth_client, owner, buyer):
    response = auth_client(owner).patch(detail(buyer), {"expected_version": 1}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    buyer.refresh_from_db()
    assert buyer.version == 1


def test_removing_the_only_contact_says_why_in_both_fields(auth_client, owner, buyer):
    response = auth_client(owner).patch(
        detail(buyer), {"phone": "", "expected_version": 1}, format="json"
    )

    assert response.status_code == 400
    assert response.data["fields"]["phone"] == CONTACT_REQUIRED
    assert response.data["fields"]["email"] == CONTACT_REQUIRED


def test_a_document_another_buyer_has_answers_409(auth_client, owner, producer, buyer):
    other = BuyerFactory(producer=producer, identity_document="800111222")

    response = auth_client(owner).patch(
        detail(buyer), {"identity_document": "800111222", "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"
    assert response.data["existing"]["id"] == str(other.pk)


def test_a_stale_version_answers_409_with_the_current_buyer(auth_client, owner, buyer):
    client = auth_client(owner)
    client.patch(detail(buyer), {"name": "Cacao Andino 2", "expected_version": 1}, format="json")

    response = client.patch(detail(buyer), {"name": "Otro", "expected_version": 1}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["name"] == "Cacao Andino 2"
    assert response.data["current"]["version"] == 2


def test_another_producers_buyer_is_not_found(auth_client, owner):
    foreign = BuyerFactory()

    response = auth_client(owner).patch(
        detail(foreign), {"name": "Xx", "expected_version": 1}, format="json"
    )

    assert response.status_code == 404
