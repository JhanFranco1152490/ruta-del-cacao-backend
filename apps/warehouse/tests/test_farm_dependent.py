"""Una finca creada por error se elimina con las bodegas que nunca recibieron un lote."""

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.farms.models import Farm
from apps.warehouse.models import Warehouse, WarehouseAuditEvent

from .factories import StockEntryFactory, WarehouseFactory

pytestmark = pytest.mark.django_db


def delete_farm(auth_client, farm):
    client = auth_client(make_producer_owner(farm.producer))
    return client.delete(f"/api/farms/{farm.pk}?expected_version={farm.version}")


def test_a_farm_is_deleted_with_its_warehouses_never_used(auth_client):
    warehouse = WarehouseFactory()
    farm = warehouse.farm

    response = delete_farm(auth_client, farm)

    assert response.status_code == 204, response.data
    assert not Farm.objects.filter(pk=farm.pk).exists()
    assert not Warehouse.objects.filter(pk=warehouse.pk).exists()
    assert WarehouseAuditEvent.objects.filter(
        warehouse_ref=warehouse.pk, action="deleted"
    ).exists()


def test_a_used_warehouse_keeps_its_farm(auth_client):
    warehouse = WarehouseFactory()
    StockEntryFactory(warehouse=warehouse, lot__harvest__plot__farm=warehouse.farm)

    response = delete_farm(auth_client, warehouse.farm)

    assert (response.status_code, response.data["code"]) == (409, "farm_has_records")
    assert Warehouse.objects.filter(pk=warehouse.pk).exists()
