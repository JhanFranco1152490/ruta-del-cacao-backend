import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import NEAR_SHAPES, PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

URL = "/api/plots"


@pytest.fixture
def client(auth_client):
    return auth_client(UserFactory(is_superuser=True))


def farm_of(producer, name):
    return FarmFactory(**NEAR_SHAPES, producer=producer, name=name)


def labels(client, **params):
    return [
        f"{plot['farm']['producer']['last_name']}/{plot['farm']['name']}/{plot['code']}"
        for plot in client.get(URL, params).data["results"]
    ]


def test_orders_by_code_by_default(client):
    farm = farm_of(ProducerFactory(), "La Esperanza")
    for code in ["P-03", "P-01", "P-02"]:
        PlotFactory(farm=farm, code=code)

    assert [label.rsplit("/", 1)[1] for label in labels(client)] == ["P-01", "P-02", "P-03"]
    assert labels(client) == labels(client, ordering="code")


def test_groups_by_producer_name_then_farm_name_then_code(client):
    zapata = ProducerFactory(last_name="Zapata", first_name="Ana")
    alvarez = ProducerFactory(last_name="Álvarez", first_name="Luis")
    PlotFactory(farm=farm_of(zapata, "Bella Vista"), code="A1")
    PlotFactory(farm=farm_of(alvarez, "Monteverde"), code="A1")
    esperanza = farm_of(alvarez, "La Esperanza")
    PlotFactory(farm=esperanza, code="B2")
    PlotFactory(farm=esperanza, code="A1")

    assert labels(client, ordering="producer,farm,code") == [
        "Álvarez/La Esperanza/A1",
        "Álvarez/La Esperanza/B2",
        "Álvarez/Monteverde/A1",
        "Zapata/Bella Vista/A1",
    ]


def test_equal_names_keep_a_stable_order_across_pages(client):
    # Dos productores con el mismo nombre y dos fincas con el mismo nombre: solo el id desempata,
    # y ninguna parcela puede repetirse ni perderse entre páginas.
    twins = [ProducerFactory(last_name="Pérez", first_name="Ana") for _ in range(2)]
    for producer in twins:
        farm = farm_of(producer, "El Mango")
        for code in ["P-01", "P-02", "P-03"]:
            PlotFactory(farm=farm, code=code)

    pages = [
        client.get(URL, {"ordering": "producer,farm,code", "page_size": 2, "page": page}).data
        for page in (1, 2, 3)
    ]
    ids = [plot["id"] for page in pages for plot in page["results"]]

    assert len(ids) == 6
    assert len(set(ids)) == 6
    producers = [plot["farm"]["producer"]["id"] for page in pages for plot in page["results"]]
    assert producers[:3] == [producers[0]] * 3
    assert producers[3:] == [producers[3]] * 3


@pytest.mark.parametrize("ordering", ["farm", "-code", "producer", "producer,farm"])
def test_an_unknown_ordering_is_rejected(client, ordering):
    response = client.get(URL, {"ordering": ordering})

    assert response.status_code == 400
    assert "ordering" in response.data["fields"]
