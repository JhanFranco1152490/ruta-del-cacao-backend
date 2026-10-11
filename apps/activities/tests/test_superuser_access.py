import pytest

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.activities.tests.test_api import URL, body
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    return UserFactory(is_superuser=True)


def test_the_technical_account_schedules_on_a_plot_of_any_producer(auth_client, superuser):
    plot = PlotFactory()
    assignee = UserFactory(producer=plot.farm.producer)

    response = auth_client(superuser).post(URL, body(plot, assignee), format="json")

    assert response.status_code == 201
    assert response.json()["producer_id"] == str(plot.farm.producer_id)


def test_the_technical_account_reads_any_activity(auth_client, superuser):
    activity = AgriculturalActivityFactory()

    response = auth_client(superuser).get(f"{URL}/{activity.pk}")

    assert response.status_code == 200


def test_the_technical_account_asks_for_the_assignees_of_a_producer(auth_client, superuser):
    plot = PlotFactory()
    UserFactory(producer=plot.farm.producer, first_name="Ana", last_name="Zapata")
    client = auth_client(superuser)

    with_producer = client.get(f"{URL}/assignees?producer={plot.farm.producer_id}")
    without = client.get(f"{URL}/assignees")

    assert [row["full_name"] for row in with_producer.json()["results"]] == ["Ana Zapata"]
    assert without.status_code == 400
    assert "producer" in without.json()["fields"]
