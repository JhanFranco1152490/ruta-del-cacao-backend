import pytest

from apps.accounts.tests.role_helpers import make_administrator, make_delegate
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(auth_client):
    return auth_client(make_administrator())


def names(response):
    assert response.status_code == 200
    return [farm["name"] for farm in response.data["results"]]


def test_filters_by_producer(admin_client):
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="Alfa")
    FarmFactory(name="Beta")

    assert names(admin_client.get(f"/api/farms?producer={producer.pk}")) == ["Alfa"]


def test_filters_by_municipality(admin_client):
    FarmFactory(name="Alfa", municipality_code="54810")
    FarmFactory(name="Beta", municipality_code="54001")

    assert names(admin_client.get("/api/farms?municipality=54810")) == ["Alfa"]


def test_ignores_spaces_around_the_municipality(admin_client):
    FarmFactory(name="Alfa", municipality_code="54810")

    assert names(admin_client.get("/api/farms?municipality=%2054810%20")) == ["Alfa"]


@pytest.mark.parametrize(
    "query, field",
    [("municipality=05001", "municipality"), ("producer=no-es-uuid", "producer")],
)
def test_rejects_malformed_filters(admin_client, query, field):
    response = admin_client.get(f"/api/farms?{query}")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert field in response.data["fields"]


@pytest.mark.parametrize(
    "path",
    ["/api/farms", "/api/farms/map/municipalities", "/api/farms/map/points?municipality=54001"],
)
def test_another_producer_filter_never_widens_an_employee_scope(auth_client, path):
    # Se rechaza en vez de responder vacío, para que el intento no pase como una consulta
    # normal; en ningún caso se ven fincas ajenas.
    own, other = ProducerFactory(), ProducerFactory()
    FarmFactory(producer=other, name="Ajena")
    employee = make_delegate(own, ["farms.view_farm"])
    separator = "&" if "?" in path else "?"

    response = auth_client(employee).get(f"{path}{separator}producer={other.pk}")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert "Ajena" not in str(response.data)


def test_an_employee_may_filter_by_its_own_producer(auth_client):
    own = ProducerFactory()
    FarmFactory(producer=own, name="Propia")
    employee = make_delegate(own, ["farms.view_farm"])

    response = auth_client(employee).get(f"/api/farms?producer={own.pk}")

    assert names(response) == ["Propia"]
