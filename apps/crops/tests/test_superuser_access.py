import pytest

from apps.accounts.tests.factories import UserFactory
from apps.crops.tests.factories import PlotCharacterizationFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]


def test_the_technical_account_reads_the_characterization_of_any_plot(auth_client):
    superuser = UserFactory(is_superuser=True)
    plot = PlotFactory()
    PlotCharacterizationFactory(plot=plot)

    response = auth_client(superuser).get(f"/api/plot-characterizations/{plot.pk}")

    assert response.status_code == 200


def test_the_technical_account_lists_the_characterizations_of_any_farm(auth_client):
    superuser = UserFactory(is_superuser=True)
    plot = PlotFactory()
    PlotCharacterizationFactory(plot=plot)

    response = auth_client(superuser).get(f"/api/plot-characterizations?farm={plot.farm_id}")

    assert response.status_code == 200
    assert len(response.data["results"]) == 1


def test_the_technical_account_lists_the_characterizations_of_plots_of_any_producer(auth_client):
    superuser = UserFactory(is_superuser=True)
    first, second = PlotFactory(), PlotFactory()
    PlotCharacterizationFactory(plot=first)
    PlotCharacterizationFactory(plot=second)

    response = auth_client(superuser).get(
        f"/api/plot-characterizations?plots={first.pk},{second.pk}"
    )

    assert {item["plot_id"] for item in response.data["results"]} == {
        str(first.pk),
        str(second.pk),
    }
