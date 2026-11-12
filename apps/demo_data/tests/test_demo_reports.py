"""Los reportes con la semilla: cada tipo tiene filas para el Productor y para el Administrador, la
asociación ve alguna finca en 0, y el capataz genera los de su finca pero no Comercialización.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_ADMIN_EMAIL, DEMO_FOREMAN_EMAIL, DEMO_PRODUCER_EMAIL
from apps.demo_data.reports import REPORTS_ROLE
from apps.demo_data.seed import seed_demo_data

pytestmark = pytest.mark.django_db

PRODUCER_URL = "/api/reports/producer"
ASSOCIATION_URL = "/api/reports/association"


@pytest.fixture
def seeded():
    seed_demo_data()


def last_year():
    today = timezone.localdate()
    return {"from": str(today - timedelta(days=365)), "to": str(today)}


def account(email):
    return User.objects.get(email=email)


@pytest.mark.parametrize("report_type", ["production", "quality", "sales", "traceability"])
def test_each_producer_report_has_rows_in_the_last_year(auth_client, seeded, report_type):
    response = auth_client(account(DEMO_PRODUCER_EMAIL)).get(
        PRODUCER_URL, {"type": report_type, **last_year()}
    )

    assert response.status_code == 200
    assert response.json()["rows"]


def test_the_inventory_has_stock_today(auth_client, seeded):
    response = auth_client(account(DEMO_PRODUCER_EMAIL)).get(PRODUCER_URL, {"type": "inventory"})

    assert response.json()["rows"]


@pytest.mark.parametrize("report_type", ["production", "quality", "sales"])
def test_each_association_report_has_rows_in_the_last_year(auth_client, seeded, report_type):
    response = auth_client(account(DEMO_ADMIN_EMAIL)).get(
        ASSOCIATION_URL, {"type": report_type, **last_year()}
    )

    assert response.status_code == 200
    assert len(response.json()["rows"]) > 1


def test_the_association_also_sees_the_farms_that_did_not_produce(auth_client, seeded):
    response = auth_client(account(DEMO_ADMIN_EMAIL)).get(
        ASSOCIATION_URL, {"type": "production", **last_year()}
    )

    # El reporte es para el seguimiento: también salen las fincas que no produjeron.
    assert any(row["green_kg"] == "0.0" for row in response.json()["rows"])


def test_the_foreman_reports_on_its_farm_but_not_on_sales(auth_client, seeded):
    foreman = account(DEMO_FOREMAN_EMAIL)

    production = auth_client(foreman).get(PRODUCER_URL, {"type": "production", **last_year()})
    sales = auth_client(foreman).get(PRODUCER_URL, {"type": "sales", **last_year()})

    assert production.status_code == 200
    assert {row["farm"].split(" · ")[1] for row in production.json()["rows"]} == {"La Esperanza"}
    assert sales.status_code == 403


def test_seeding_again_keeps_one_reports_role_and_the_foreman_role(seeded):
    seed_demo_data()

    foreman = account(DEMO_FOREMAN_EMAIL)
    names = sorted(foreman.groups.values_list("role__name", flat=True))
    assert names == ["Capataz/Operario", REPORTS_ROLE]
