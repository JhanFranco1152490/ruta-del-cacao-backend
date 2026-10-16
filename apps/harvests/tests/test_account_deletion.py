"""Una cuenta recolectora es parte de una cosecha: no se elimina, se desactiva."""

import pytest

from apps.accounts.models import User
from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_an_account_that_collected_a_harvest_is_not_deleted(auth_client):
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    collector = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))
    HarvestFactory(plot=characterized_plot(farm=farm), collector=collector)

    response = auth_client(make_producer_owner(producer)).delete(f"/api/users/{collector.pk}")

    assert response.status_code == 409
    assert response.data["code"] == "account_has_activity"
    assert User.objects.filter(pk=collector.pk).exists()


def test_an_account_that_only_registered_a_harvest_is_deleted_and_the_harvest_stays(auth_client):
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    registrar = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))
    harvest = HarvestFactory(plot=characterized_plot(farm=farm), registered_by=registrar)

    response = auth_client(make_producer_owner(producer)).delete(f"/api/users/{registrar.pk}")

    assert response.status_code == 204
    harvest.refresh_from_db()
    assert harvest.registered_by is None
