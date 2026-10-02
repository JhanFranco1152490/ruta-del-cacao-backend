import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

COUNTS = "/api/farms/map/municipalities"
POINTS = "/api/farms/map/points"


@pytest.fixture
def admin_client(auth_client):
    return auth_client(make_administrator())


def test_counts_farms_per_municipality(admin_client):
    FarmFactory(municipality_code="54810")
    FarmFactory(municipality_code="54810", is_active=False)
    FarmFactory(municipality_code="54001")

    response = admin_client.get(COUNTS)

    assert response.status_code == 200
    assert response.data == [
        {"municipality_id": "54001", "farm_count": 1},
        {"municipality_id": "54810", "farm_count": 2},
    ]


def test_counts_respect_the_producer_scope(auth_client):
    producer = ProducerFactory()
    FarmFactory(producer=producer, municipality_code="54810")
    FarmFactory(municipality_code="54001")

    response = auth_client(make_producer_owner(producer)).get(COUNTS)

    assert response.data == [{"municipality_id": "54810", "farm_count": 1}]


def test_counts_apply_the_list_filters(admin_client):
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="Alfa", municipality_code="54810")
    FarmFactory(producer=producer, name="Beta", municipality_code="54001")
    FarmFactory(name="Alfa dos", municipality_code="54001")

    response = admin_client.get(f"{COUNTS}?producer={producer.pk}&search=alfa")

    assert response.data == [{"municipality_id": "54810", "farm_count": 1}]


def test_points_of_a_municipality(admin_client):
    producer = ProducerFactory(first_name="Ana", last_name="Rojas")
    FarmFactory(producer=producer, name="Beta", municipality_code="54810", is_active=False)
    FarmFactory(producer=producer, name="Alfa", municipality_code="54810")
    FarmFactory(name="Fuera", municipality_code="54001")

    response = admin_client.get(f"{POINTS}?municipality=54810")

    assert response.status_code == 200
    assert [point["name"] for point in response.data] == ["Alfa", "Beta"]
    beta = response.data[1]
    assert beta["is_active"] is False
    assert beta["location"] == {"latitude": "7.8234567", "longitude": "-72.5123456"}
    assert beta["producer"] == {
        "id": str(producer.pk),
        "member_code": producer.member_code,
        "first_name": "Ana",
        "last_name": "Rojas",
    }


def test_points_without_municipality_cover_the_whole_scope(admin_client):
    FarmFactory(name="Alfa", municipality_code="54810")
    FarmFactory(name="Beta", municipality_code="54001")

    response = admin_client.get(POINTS)

    assert response.status_code == 200
    assert [point["name"] for point in response.data] == ["Alfa", "Beta"]


def test_points_reject_an_unknown_municipality(admin_client):
    response = admin_client.get(f"{POINTS}?municipality=05001")

    assert response.status_code == 400
    assert "municipality" in response.data["fields"]


@pytest.mark.parametrize("path", [COUNTS, f"{POINTS}?municipality=54810"])
def test_map_requires_the_view_permission(auth_client, path):
    response = auth_client(UserFactory(producer=ProducerFactory())).get(path)

    assert response.status_code == 403


@pytest.mark.parametrize("path", [COUNTS, f"{POINTS}?municipality=54810"])
def test_map_queries_do_not_grow_with_the_farms(admin_client, path):
    FarmFactory(municipality_code="54810")
    with CaptureQueriesContext(connection) as one:
        admin_client.get(path)
    FarmFactory.create_batch(5, municipality_code="54810")
    with CaptureQueriesContext(connection) as many:
        admin_client.get(path)

    assert len(many) == len(one)
