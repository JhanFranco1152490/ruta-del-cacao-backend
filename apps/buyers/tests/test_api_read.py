import pytest

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db

URL = "/api/buyers"


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


def sales_manager_of(producer, farm):
    return grant_role(UserFactory(producer=producer, farm=farm), get_system_role(SALES_MANAGER))


def test_every_read_needs_a_session(anonymous_client, buyer):
    assert anonymous_client.get(URL).status_code == 401
    assert anonymous_client.get(detail(buyer)).status_code == 401


def test_the_association_has_no_access_to_buyers(auth_client, buyer):
    client = auth_client(make_administrator())

    assert client.get(URL).status_code == 403
    assert client.get(detail(buyer)).status_code == 403


def test_an_employee_without_the_permission_cannot_read(auth_client, producer, buyer):
    stranger = make_delegate(producer, ["farms.view_farm"], all_farms=True)

    assert auth_client(stranger).get(URL).status_code == 403


def test_list_returns_the_whole_directory_ordered_by_name_without_pagination(
    auth_client, owner, producer
):
    BuyerFactory(producer=producer, name="zafra Exportaciones")
    BuyerFactory(producer=producer, name="Aroma", is_active=False)
    BuyerFactory(name="De otro productor")

    response = auth_client(owner).get(URL)

    assert response.status_code == 200
    assert set(response.data) == {"results"}
    assert [row["name"] for row in response.data["results"]] == ["Aroma", "zafra Exportaciones"]
    assert "no-store" in response["Cache-Control"]


def test_the_representation_has_the_documented_shape(auth_client, owner, producer):
    buyer = BuyerFactory(
        producer=producer,
        name="Chocolates del Oriente S.A.S.",
        document_type="NIT",
        identity_document="900123456",
        buyer_type="exporter",
        contact_name="Persona de Ejemplo",
        phone=None,
        email="compras@example.com",
    )

    row = auth_client(owner).get(detail(buyer)).data

    assert set(row) == {
        "id",
        "producer",
        "name",
        "document_type",
        "identity_document",
        "buyer_type",
        "contact_name",
        "phone",
        "email",
        "is_active",
        "has_records",
        "version",
        "created_at",
        "updated_at",
    }
    assert row["producer"] == {
        "id": str(producer.pk),
        "member_code": producer.member_code,
        "first_name": producer.first_name,
        "last_name": producer.last_name,
    }
    assert (row["document_type"], row["identity_document"]) == ("NIT", "900123456")
    assert (row["phone"], row["email"]) == (None, "compras@example.com")
    assert row["has_records"] is False


def test_has_records_is_true_for_a_buyer_with_sales(
    auth_client, owner, producer, buyer_usage_table
):
    sold_to = BuyerFactory(producer=producer)
    buyer_usage_table(sold_to)

    assert auth_client(owner).get(detail(sold_to)).data["has_records"] is True
    rows = auth_client(owner).get(URL).data["results"]
    assert [row["has_records"] for row in rows] == [True]


def test_the_list_does_not_query_once_per_buyer(
    auth_client, owner, producer, buyer_usage_table, django_assert_max_num_queries
):
    for _ in range(5):
        buyer_usage_table(BuyerFactory(producer=producer))
    client = auth_client(owner)
    client.get(URL)

    with django_assert_max_num_queries(8):
        response = client.get(URL)

    assert len(response.data["results"]) == 5


def test_sales_managers_of_different_farms_see_the_same_directory(auth_client, producer, buyer):
    first = sales_manager_of(producer, FarmFactory(producer=producer))
    second = sales_manager_of(producer, FarmFactory(producer=producer))

    for manager in (first, second):
        rows = auth_client(manager).get(URL).data["results"]
        assert [row["id"] for row in rows] == [str(buyer.pk)]
        assert auth_client(manager).get(detail(buyer)).status_code == 200


def test_another_producers_buyer_is_not_found(auth_client, owner):
    foreign = BuyerFactory()

    assert auth_client(owner).get(detail(foreign)).status_code == 404


def test_an_id_that_is_not_a_uuid_is_not_found(auth_client, owner):
    assert auth_client(owner).get(f"{URL}/no-es-un-id").status_code == 404


def test_the_producer_filter_is_ignored_for_regular_accounts(auth_client, owner, buyer):
    other = ProducerFactory()
    BuyerFactory(producer=other)

    response = auth_client(owner).get(URL, {"producer": str(other.pk)})

    assert [row["id"] for row in response.data["results"]] == [str(buyer.pk)]


def test_a_malformed_producer_filter_is_a_validation_error(auth_client, owner):
    response = auth_client(owner).get(URL, {"producer": "x"})

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_the_technical_account_sees_every_producer_or_the_one_it_names(auth_client, buyer):
    other = BuyerFactory(name="Bocadillos")
    client = auth_client(UserFactory(is_superuser=True))

    everyone = client.get(URL).data["results"]
    named = client.get(URL, {"producer": str(other.producer_id)}).data["results"]

    assert {row["id"] for row in everyone} == {str(buyer.pk), str(other.pk)}
    assert [row["id"] for row in named] == [str(other.pk)]
    assert client.get(detail(buyer)).status_code == 200
