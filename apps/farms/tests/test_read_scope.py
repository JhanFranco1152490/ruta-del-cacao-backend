import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def farms():
    first, second = ProducerFactory(), ProducerFactory()
    return {
        "first": FarmFactory(producer=first, name="Alfa"),
        "second": FarmFactory(producer=second, name="Beta"),
    }


def listed_names(client):
    response = client.get("/api/farms")
    assert response.status_code == 200
    return [farm["name"] for farm in response.data["results"]]


def test_association_admin_reads_every_producer_farms(auth_client, farms):
    assert listed_names(auth_client(make_administrator())) == ["Alfa", "Beta"]


def test_association_admin_reads_a_farm_of_any_producer(auth_client, farms):
    response = auth_client(make_administrator()).get(f"/api/farms/{farms['second'].pk}")

    assert response.status_code == 200
    assert response.data["name"] == "Beta"


def test_association_admin_cannot_edit_without_the_change_permission(auth_client, farms):
    response = auth_client(make_administrator()).patch(
        f"/api/farms/{farms['first'].pk}",
        {"name": "Otra", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 403


def test_producer_reads_only_its_farms(auth_client, farms):
    owner = make_producer_owner(farms["first"].producer)

    assert listed_names(auth_client(owner)) == ["Alfa"]


def test_employee_reads_only_its_producer_farms(auth_client, farms):
    employee = make_delegate(farms["second"].producer, ["farms.view_farm"])

    assert listed_names(auth_client(employee)) == ["Beta"]


def test_account_without_producer_or_admin_role_reads_nothing(auth_client, farms):
    stray = UserFactory(permissions=["farms.view_farm"])

    assert listed_names(auth_client(stray)) == []
