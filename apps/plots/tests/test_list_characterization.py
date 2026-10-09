import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.crops.tests.factories import PlotCharacterizationFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import NEAR_SHAPES, PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

URL = "/api/plots"


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory(), permissions=["plots.view_plot"])


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def farm(owner):
    return FarmFactory(**NEAR_SHAPES, producer=owner.producer)


def characterized(farm, code, **fields):
    plot = PlotFactory(farm=farm, code=code, **fields)
    PlotCharacterizationFactory(plot=plot)
    return plot


def codes(client, **params):
    return [plot["code"] for plot in client.get(URL, params).data["results"]]


def test_filters_the_plots_with_and_without_characterization(client, farm):
    characterized(farm, "P-01")
    PlotFactory(farm=farm, code="P-02")

    assert codes(client, characterization="done") == ["P-01"]
    assert codes(client, characterization="pending") == ["P-02"]
    assert codes(client) == ["P-01", "P-02"]


def test_counts_every_page_and_ignores_the_characterization_filter(client, farm):
    characterized(farm, "P-01")
    characterized(farm, "P-02")
    PlotFactory(farm=farm, code="P-03")

    response = client.get(URL, {"characterization": "pending", "page_size": 1})

    assert response.data["count"] == 1
    assert response.data["characterization_counts"] == {"done": 2, "pending": 1}


def test_the_counts_follow_the_other_filters(client, farm):
    characterized(farm, "P-01")
    characterized(farm, "P-02", is_active=False)
    PlotFactory(farm=farm, code="P-03", is_active=False)
    other_farm = FarmFactory(**NEAR_SHAPES, producer=farm.producer)
    PlotFactory(farm=other_farm, code="P-04")

    def counts(**params):
        return client.get(URL, params).data["characterization_counts"]

    assert counts() == {"done": 2, "pending": 2}
    assert counts(is_active="true") == {"done": 1, "pending": 1}
    assert counts(farm=farm.pk) == {"done": 2, "pending": 1}
    assert counts(search="P-04") == {"done": 0, "pending": 1}


def test_the_counts_stay_within_the_session_producer(client, farm):
    characterized(farm, "P-01")
    characterized(FarmFactory(**NEAR_SHAPES, producer=ProducerFactory()), "Ajena")

    assert client.get(URL).data["characterization_counts"] == {"done": 1, "pending": 0}


def test_the_technical_account_counts_one_producer_or_everyone(auth_client, farm):
    characterized(farm, "P-01")
    PlotFactory(farm=FarmFactory(**NEAR_SHAPES, producer=ProducerFactory()), code="Ajena")
    client = auth_client(UserFactory(is_superuser=True))

    everyone = client.get(URL).data["characterization_counts"]
    one = client.get(URL, {"producer": farm.producer_id}).data["characterization_counts"]

    assert everyone == {"done": 1, "pending": 1}
    assert one == {"done": 1, "pending": 0}


def test_an_unknown_characterization_value_is_rejected(client):
    response = client.get(URL, {"characterization": "con_error"})

    assert response.status_code == 400
    assert "characterization" in response.data["fields"]


def test_filtering_and_counting_take_the_same_queries_with_one_or_many_plots(client, farm):
    characterized(farm, "P-01")
    with CaptureQueriesContext(connection) as one:
        client.get(URL, {"characterization": "done"})
    for number in range(2, 7):
        characterized(farm, f"P-0{number}")
        PlotFactory(farm=farm, code=f"Q-0{number}")

    with CaptureQueriesContext(connection) as many:
        client.get(URL, {"characterization": "done"})

    assert len(many) == len(one)
