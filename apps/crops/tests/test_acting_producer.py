import pytest

from apps.accounts.tests.factories import UserFactory
from apps.crops.tests.factories import PlotCharacterizationFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]


def test_the_superuser_reads_a_characterization_only_under_the_producer_of_its_plot(auth_client):
    superuser = UserFactory(is_superuser=True)
    plot = PlotFactory()
    PlotCharacterizationFactory(plot=plot)
    url = f"/api/plot-characterizations/{plot.pk}"

    without = auth_client(superuser).get(url)
    under = auth_client(superuser).get(url, HTTP_X_ACTING_PRODUCER=str(plot.farm.producer_id))

    assert without.status_code == 404
    assert under.status_code == 200
