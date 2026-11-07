"""Las bodegas de una finca: registrar, consultar, editar, activar y eliminar."""

import pytest

from apps.accounts.system_roles import QUALITY_MANAGER, SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory
from apps.warehouse.models import StockEntry, Warehouse, WarehouseAuditEvent

from .factories import StockEntryFactory, WarehouseFactory

pytestmark = pytest.mark.django_db

URL = "/api/warehouses"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def other_farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def inspector(producer, farm):
    return grant_role(UserFactory(producer=producer, farm=farm), get_system_role(QUALITY_MANAGER))


@pytest.fixture
def warehouse(farm):
    return WarehouseFactory(farm=farm, name="Bodega principal", name_normalized="bodegaprincipal")


def detail(warehouse) -> str:
    return f"{URL}/{warehouse.pk}"


def create(client, farm, name="Bodega principal"):
    return client.post(URL, {"farm_id": str(farm.pk), "name": name}, format="json")


# --- Sesión y permisos ---


def test_every_read_needs_a_session(anonymous_client, warehouse):
    assert anonymous_client.get(URL).status_code == 401
    assert anonymous_client.get(detail(warehouse)).status_code == 401


def test_the_association_has_no_access(auth_client, warehouse):
    client = auth_client(make_administrator())

    assert client.get(URL).status_code == 403
    assert client.get(detail(warehouse)).status_code == 403


def test_the_sales_manager_reads_the_warehouses_but_does_not_write(
    auth_client, producer, farm, warehouse
):
    sales = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(SALES_MANAGER))
    client = auth_client(sales)

    assert client.get(URL).status_code == 200
    assert create(client, farm, "Otra").status_code == 403
    assert (
        client.patch(
            detail(warehouse), {"expected_version": 1, "name": "X"}, format="json"
        ).status_code
        == 403
    )
    assert client.delete(f"{detail(warehouse)}?expected_version=1").status_code == 403


def test_a_delegate_with_only_view_stock_cannot_manage(auth_client, producer, farm, warehouse):
    viewer = make_delegate(producer, ["warehouse.view_stock"], farm=farm)

    assert create(auth_client(viewer), farm, "Otra").status_code == 403


# --- Registrar ---


def test_registering_a_warehouse_leaves_it_active_and_unused(auth_client, owner, farm):
    response = create(auth_client(owner), farm)

    assert response.status_code == 201, response.data
    assert response.data["name"] == "Bodega principal"
    assert (response.data["is_active"], response.data["in_use"], response.data["version"]) == (
        True,
        False,
        1,
    )
    assert response.data["farm"]["id"] == str(farm.pk)
    assert response["Location"].endswith(f"{URL}/{response.data['id']}")


def test_registering_leaves_the_history(auth_client, owner, farm):
    response = create(auth_client(owner), farm)

    event = WarehouseAuditEvent.objects.get(warehouse_ref=response.data["id"])
    assert (event.action, event.actor, event.warehouse_name) == (
        "created",
        owner,
        "Bodega principal",
    )
    assert event.farm_ref == farm.pk
    assert event.changes["name"] == {"before": None, "after": "Bodega principal"}


def test_the_quality_manager_registers_in_its_farm_only(auth_client, inspector, farm, other_farm):
    client = auth_client(inspector)

    assert create(client, farm).status_code == 201
    assert create(client, other_farm).status_code == 404


def test_the_name_is_not_repeated_in_a_farm_whatever_the_case_or_accents(
    auth_client, owner, farm, warehouse
):
    response = create(auth_client(owner), farm, "  BODEGA  Principal ")

    assert response.status_code == 409
    assert response.data["code"] == "warehouse_name_taken"
    assert response.data["fields"]["name"]
    assert response.data["existing"]["id"] == str(warehouse.pk)


def test_the_same_name_is_fine_in_another_farm(auth_client, owner, farm, other_farm, warehouse):
    assert create(auth_client(owner), other_farm).status_code == 201


@pytest.mark.parametrize("name", ["", "   ", " - ", "x" * 41])
def test_an_empty_or_long_name_is_refused(auth_client, owner, farm, name):
    response = create(auth_client(owner), farm, name)

    assert response.status_code == 400
    assert "name" in response.data["fields"]


def test_an_unknown_field_is_refused(auth_client, owner, farm):
    response = auth_client(owner).post(
        URL, {"farm_id": str(farm.pk), "name": "X", "capacity_kg": "100"}, format="json"
    )

    assert response.status_code == 400


def test_a_farm_of_another_producer_does_not_exist_for_the_caller(auth_client, owner):
    foreign = FarmFactory()

    assert create(auth_client(owner), foreign).status_code == 404


def test_an_inactive_farm_gets_no_new_warehouse(auth_client, owner, farm):
    farm.is_active = False
    farm.save(update_fields=["is_active"])

    response = create(auth_client(owner), farm)

    assert (response.status_code, response.data["code"]) == (422, "farm_inactive")


def test_an_employee_without_a_farm_is_told_so(auth_client, producer):
    drifter = make_delegate(producer, ["warehouse.manage_warehouse"])

    response = create(auth_client(drifter), FarmFactory(producer=producer))

    assert response.status_code == 403


# --- Consultar ---


def test_the_list_is_paginated_by_farm_and_name(auth_client, owner, farm, other_farm):
    WarehouseFactory(farm=other_farm, name="Anexo", name_normalized="anexo")
    WarehouseFactory(farm=farm, name="Zeta", name_normalized="zeta")
    WarehouseFactory(farm=farm, name="Alfa", name_normalized="alfa")

    response = auth_client(owner).get(URL)

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert [row["name"] for row in response.data["results"]] == ["Alfa", "Zeta", "Anexo"]


def test_the_list_filters_by_farm_state_and_name(auth_client, owner, farm, other_farm, warehouse):
    inactive = WarehouseFactory(farm=farm, name="Vieja", name_normalized="vieja", is_active=False)
    WarehouseFactory(farm=other_farm, name="Anexo", name_normalized="anexo")
    client = auth_client(owner)

    def names(**params):
        return {row["name"] for row in client.get(URL, params).data["results"]}

    assert names(farm=str(farm.pk)) == {"Bodega principal", "Vieja"}
    assert names(active="true") == {"Bodega principal", "Anexo"}
    assert names(active="false") == {inactive.name}
    assert names(search="PRINC") == {"Bodega principal"}


def test_an_employee_reads_only_the_warehouses_of_its_farms(
    auth_client, inspector, farm, other_farm, warehouse
):
    WarehouseFactory(farm=other_farm)

    response = auth_client(inspector).get(URL)

    assert [row["id"] for row in response.data["results"]] == [str(warehouse.pk)]


def test_a_warehouse_of_another_producer_is_not_found(auth_client, owner):
    foreign = WarehouseFactory()

    assert auth_client(owner).get(detail(foreign)).status_code == 404


def test_the_technical_account_chooses_the_producer(auth_client, warehouse):
    other = WarehouseFactory()
    technical = UserFactory(is_superuser=True, producer=None)
    client = auth_client(technical)

    assert client.get(URL).data["count"] == 2
    scoped = client.get(URL, {"producer": str(other.farm.producer_id)})
    assert [row["id"] for row in scoped.data["results"]] == [str(other.pk)]


def test_in_use_says_whether_the_warehouse_ever_received_a_lot(auth_client, owner, warehouse):
    client = auth_client(owner)
    assert client.get(detail(warehouse)).data["in_use"] is False

    StockEntryFactory(warehouse=warehouse, lot__harvest__plot__farm=warehouse.farm)

    assert client.get(detail(warehouse)).data["in_use"] is True


# --- Editar, activar y desactivar ---


def test_renaming_raises_the_version_and_leaves_the_history(auth_client, owner, warehouse):
    response = auth_client(owner).patch(
        detail(warehouse), {"expected_version": 1, "name": "Bodega central"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert (response.data["name"], response.data["version"]) == ("Bodega central", 2)
    event = WarehouseAuditEvent.objects.get(warehouse=warehouse, action="updated")
    assert event.changes["name"] == {"before": "Bodega principal", "after": "Bodega central"}


def test_deactivating_and_activating_leave_their_own_events(auth_client, owner, warehouse):
    client = auth_client(owner)

    off = client.patch(
        detail(warehouse), {"expected_version": 1, "is_active": False}, format="json"
    )
    on = client.patch(detail(warehouse), {"expected_version": 2, "is_active": True}, format="json")

    assert (off.data["is_active"], on.data["is_active"]) == (False, True)
    assert (
        WarehouseAuditEvent.objects.filter(warehouse=warehouse, action="status_changed").count()
        == 2
    )


def test_editing_without_changes_writes_nothing(auth_client, owner, warehouse):
    response = auth_client(owner).patch(
        detail(warehouse), {"expected_version": 1, "name": "  Bodega principal "}, format="json"
    )

    assert response.status_code == 200
    assert response.data["version"] == 1
    assert not WarehouseAuditEvent.objects.filter(warehouse=warehouse, action="updated").exists()


def test_renaming_to_a_name_in_use_is_refused(auth_client, owner, farm, warehouse):
    other = WarehouseFactory(farm=farm, name="Anexo", name_normalized="anexo")

    response = auth_client(owner).patch(
        detail(other), {"expected_version": 1, "name": "bodega principal"}, format="json"
    )

    assert (response.status_code, response.data["code"]) == (409, "warehouse_name_taken")


def test_a_stale_version_returns_the_current_warehouse(auth_client, owner, warehouse):
    client = auth_client(owner)
    client.patch(detail(warehouse), {"expected_version": 1, "name": "Nueva"}, format="json")

    response = client.patch(
        detail(warehouse), {"expected_version": 1, "name": "Otra"}, format="json"
    )

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["name"] == "Nueva"


def test_the_farm_cannot_be_changed(auth_client, owner, other_farm, warehouse):
    response = auth_client(owner).patch(
        detail(warehouse),
        {"expected_version": 1, "farm_id": str(other_farm.pk)},
        format="json",
    )

    assert response.status_code == 400


def test_a_patch_needs_the_version_and_a_change(auth_client, owner, warehouse):
    client = auth_client(owner)

    assert client.patch(detail(warehouse), {"name": "X"}, format="json").status_code == 400
    assert (
        client.patch(detail(warehouse), {"expected_version": 1}, format="json").status_code == 400
    )


# --- Eliminar ---


def test_a_warehouse_never_used_is_deleted_and_its_history_stays(auth_client, owner, warehouse):
    response = auth_client(owner).delete(f"{detail(warehouse)}?expected_version=1")

    assert response.status_code == 204
    assert not Warehouse.objects.filter(pk=warehouse.pk).exists()
    event = WarehouseAuditEvent.objects.get(warehouse_ref=warehouse.pk, action="deleted")
    assert (event.warehouse, event.warehouse_name) == (None, "Bodega principal")


def test_a_warehouse_that_received_a_lot_cannot_be_deleted(auth_client, owner, warehouse):
    StockEntryFactory(warehouse=warehouse, lot__harvest__plot__farm=warehouse.farm)

    response = auth_client(owner).delete(f"{detail(warehouse)}?expected_version=1")

    assert (response.status_code, response.data["code"]) == (409, "warehouse_has_records")
    assert Warehouse.objects.filter(pk=warehouse.pk).exists()
    assert StockEntry.objects.exists()


def test_deleting_with_a_stale_version_is_refused(auth_client, owner, warehouse):
    response = auth_client(owner).delete(f"{detail(warehouse)}?expected_version=9")

    assert (response.status_code, response.data["code"]) == (409, "stale_version")


def test_deleting_needs_the_version(auth_client, owner, warehouse):
    assert auth_client(owner).delete(detail(warehouse)).status_code == 400
