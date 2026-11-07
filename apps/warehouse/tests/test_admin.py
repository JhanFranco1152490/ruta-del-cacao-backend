import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.warehouse.models import Warehouse, WarehouseAuditEvent

from .factories import StockEntryFactory, WarehouseFactory
from .helpers import WarehouseEstate

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def client(superuser):
    client = Client()
    client.force_login(superuser)
    return client


def warehouse_url(name, warehouse):
    return reverse(f"admin:warehouse_warehouse_{name}", args=[warehouse.pk])


def form(warehouse, **overrides):
    data = {
        "name": warehouse.name,
        "is_active": "on" if warehouse.is_active else "",
        "expected_version": warehouse.version,
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


def test_the_list_opens_and_searches_by_name(client):
    WarehouseFactory(name="Bodega del patio", name_normalized="bodegadelpatio")
    WarehouseFactory(name="Anexo", name_normalized="anexo")

    found = client.get(reverse("admin:warehouse_warehouse_changelist"), {"q": "patio"})

    assert "Bodega del patio" in found.content.decode()
    assert "Anexo" not in found.content.decode()


def test_saving_goes_through_the_service_and_the_history_names_the_admin(client, superuser):
    warehouse = WarehouseFactory(name="Bodega 1")

    response = client.post(warehouse_url("change", warehouse), form(warehouse, name="Bodega 2"))

    assert response.status_code == 302
    warehouse.refresh_from_db()
    assert (warehouse.name, warehouse.version) == ("Bodega 2", 2)
    event = WarehouseAuditEvent.objects.get(warehouse=warehouse, action="updated")
    assert event.actor == superuser


def test_a_stale_form_is_rejected_and_changes_nothing(client):
    warehouse = WarehouseFactory(name="Bodega 1")
    stale = form(warehouse, name="Tardío")
    Warehouse.objects.filter(pk=warehouse.pk).update(version=2)

    response = client.post(warehouse_url("change", warehouse), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    warehouse.refresh_from_db()
    assert (warehouse.name, warehouse.version) == ("Bodega 1", 2)


def test_a_repeated_name_is_refused_with_the_services_message(client):
    warehouse = WarehouseFactory(name="Bodega 1")
    WarehouseFactory(farm=warehouse.farm, name="Anexo", name_normalized="anexo")

    response = client.post(
        warehouse_url("change", warehouse), form(warehouse, name="ANEXO"), follow=True
    )

    assert "Ya existe una bodega con este nombre en la finca." in response.content.decode()
    warehouse.refresh_from_db()
    assert warehouse.name == "Bodega 1"


def test_nothing_is_added_from_the_admin(client):
    assert client.get(reverse("admin:warehouse_warehouse_add")).status_code == 403


def test_deleting_goes_through_the_service(client):
    warehouse = WarehouseFactory()

    response = client.post(warehouse_url("delete", warehouse), {"post": "yes"})

    assert response.status_code == 302
    assert not Warehouse.objects.filter(pk=warehouse.pk).exists()
    assert WarehouseAuditEvent.objects.filter(
        warehouse_ref=warehouse.pk, action="deleted"
    ).exists()


def test_a_used_warehouse_is_not_deleted_and_the_reason_is_shown(client):
    warehouse = WarehouseFactory()
    StockEntryFactory(warehouse=warehouse, lot__harvest__plot__farm=warehouse.farm)

    response = client.post(warehouse_url("delete", warehouse), {"post": "yes"}, follow=True)

    assert "ya recibió ingresos" in response.content.decode()
    assert Warehouse.objects.filter(pk=warehouse.pk).exists()


def test_the_movements_are_read_only(client):
    estate = WarehouseEstate()

    for name in ("stockentry", "stockbalance", "stockexit", "stockauditevent"):
        listed = client.get(reverse(f"admin:warehouse_{name}_changelist"))
        assert listed.status_code == 200, name
        assert client.get(reverse(f"admin:warehouse_{name}_add")).status_code == 403, name
    entry = client.get(reverse("admin:warehouse_stockentry_change", args=[estate.stored.pk]))
    assert entry.status_code == 200
    assert client.post(
        reverse("admin:warehouse_stockentry_change", args=[estate.stored.pk]), {"location": "X"}
    ).status_code in (302, 403)
    estate.entry.refresh_from_db()
    assert estate.entry.location == "Estante 3"
