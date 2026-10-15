"""Cada finca tiene sus insumos: un empleado ve y toca solo los de la finca en la que trabaja.

El catálogo se guarda una vez por productor. Un insumo es de una finca cuando tiene existencias en
ella, aunque estén en cero.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.inputs.models import AgriculturalInput, InputStock
from apps.inputs.services import register_movement
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory, input_data

pytestmark = pytest.mark.django_db

INPUTS = "/api/agricultural-inputs"
STOCKS = "/api/input-stocks"
MOVEMENTS = "/api/input-movements"


def stocked(item, farm, actor, quantity="50"):
    """Deja `quantity` del insumo en la finca, con una entrada real."""
    register_movement(
        actor,
        {
            "input_id": item.pk,
            "farm_id": farm.pk,
            "kind": "entry",
            "quantity": Decimal(quantity),
            "occurred_on": timezone.localdate(),
        },
    )


class Stores:
    """Urea en las dos fincas, Cal solo en La Esperanza y Fungicida solo en El Recreo."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.owner = make_producer_owner(self.producer)
        self.esperanza = FarmFactory(producer=self.producer, name="La Esperanza")
        self.recreo = FarmFactory(producer=self.producer, name="El Recreo")
        self.urea = AgriculturalInputFactory(producer=self.producer, name="Urea")
        self.lime = AgriculturalInputFactory(producer=self.producer, name="Cal")
        self.fungicide = AgriculturalInputFactory(
            producer=self.producer, name="Fungicida", input_type="fungicide", unit="l"
        )
        stocked(self.urea, self.esperanza, self.owner, "50")
        stocked(self.urea, self.recreo, self.owner, "20")
        stocked(self.lime, self.esperanza, self.owner, "30")
        stocked(self.fungicide, self.recreo, self.owner, "8")
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.esperanza), get_system_role(FOREMAN)
        )


@pytest.fixture
def stores():
    return Stores()


def names(response) -> list[str]:
    assert response.status_code == 200, response.data
    return [row["name"] for row in response.data["results"]]


def entry(item, farm, quantity="5") -> dict:
    return {
        "input_id": str(item.pk),
        "farm_id": str(farm.pk),
        "kind": "entry",
        "quantity": quantity,
        "occurred_on": str(timezone.localdate()),
    }


# --- Lo que ve ---


def test_an_employee_sees_only_the_inputs_of_its_farm(auth_client, stores):
    client = auth_client(stores.foreman)

    assert names(client.get(INPUTS)) == ["Cal", "Urea"]
    assert client.get(f"{INPUTS}/{stores.fungicide.pk}").status_code == 404


def test_an_employee_sees_only_the_stock_of_its_farm(auth_client, stores):
    client = auth_client(stores.foreman)

    rows = client.get(STOCKS).data["results"]

    assert {(row["farm_id"], row["quantity"]) for row in rows} == {
        (str(stores.esperanza.pk), "50.000"),
        (str(stores.esperanza.pk), "30.000"),
    }
    assert client.get(STOCKS, {"farm": str(stores.recreo.pk)}).data["results"] == []


def test_an_employee_reads_the_movements_of_its_farm_only(auth_client, stores):
    client = auth_client(stores.foreman)

    def movements(farm):
        return client.get(MOVEMENTS, {"input": str(stores.urea.pk), "farm": str(farm.pk)})

    assert movements(stores.esperanza).status_code == 200
    assert movements(stores.recreo).status_code == 404


def test_the_producer_sees_the_whole_catalog_and_every_farm(auth_client, stores):
    client = auth_client(stores.owner)

    assert names(client.get(INPUTS)) == ["Cal", "Fungicida", "Urea"]
    assert len(client.get(STOCKS).data["results"]) == 4


def test_an_input_that_ran_out_stays_in_the_farm(auth_client, stores):
    register_movement(
        stores.owner,
        {
            "input_id": stores.lime.pk,
            "farm_id": stores.esperanza.pk,
            "kind": "count",
            "counted_quantity": Decimal("0"),
            "occurred_on": timezone.localdate(),
        },
    )

    assert "Cal" in names(auth_client(stores.foreman).get(INPUTS))


def test_an_employee_without_a_farm_sees_no_inputs(auth_client, stores):
    unassigned = grant_role(UserFactory(producer=stores.producer), get_system_role(FOREMAN))
    client = auth_client(unassigned)

    assert names(client.get(INPUTS)) == []
    assert client.get(STOCKS).data["results"] == []
    assert client.post(INPUTS, input_data(name="Cobre"), format="json").status_code == 403


# --- Registrar ---


def test_an_input_registered_by_an_employee_is_in_its_farm_from_the_start(auth_client, stores):
    client = auth_client(stores.foreman)

    created = client.post(INPUTS, input_data(name="Cobre"), format="json")

    assert created.status_code == 201
    assert "Cobre" in names(client.get(INPUTS))
    # Sin movimientos todavía: las existencias no lo listan, para que se vea «Sin movimientos».
    assert created.data["has_records"] is False
    stock_ids = {row["input_id"] for row in client.get(STOCKS).data["results"]}
    assert created.data["id"] not in stock_ids
    # El capataz de la otra finca no lo ve.
    other = grant_role(
        UserFactory(producer=stores.producer, farm=stores.recreo), get_system_role(FOREMAN)
    )
    assert "Cobre" not in names(auth_client(other).get(INPUTS))


def test_an_input_registered_by_the_producer_is_in_no_farm_yet(auth_client, stores):
    created = auth_client(stores.owner).post(INPUTS, input_data(name="Cobre"), format="json")

    assert created.status_code == 201
    assert not InputStock.objects.filter(input_id=created.data["id"]).exists()


def test_a_repeated_name_points_to_the_one_in_the_catalog(auth_client, stores):
    response = auth_client(stores.foreman).post(
        INPUTS, input_data(name="fungicida", input_type="fungicide", unit="l"), format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_input"
    # Con su id: la pantalla ofrece registrarle una entrada en la finca en vez de crear otro.
    assert response.data["existing"]["id"] == str(stores.fungicide.pk)


# --- Traer un insumo de otra finca ---


def test_the_catalog_search_finds_inputs_of_other_farms_without_quantities(auth_client, stores):
    response = auth_client(stores.foreman).get(f"{INPUTS}/catalog", {"search": "fungi"})

    assert response.status_code == 200
    [found] = response.data["results"]
    assert found["id"] == str(stores.fungicide.pk)
    assert set(found) == {"id", "name", "input_type", "unit", "package_type", "package_size"}


def test_the_catalog_search_needs_two_characters_and_skips_inactive_inputs(auth_client, stores):
    AgriculturalInputFactory(producer=stores.producer, name="Fungicida viejo", is_active=False)
    AgriculturalInputFactory(name="Fungicida ajeno")
    client = auth_client(stores.foreman)

    assert client.get(f"{INPUTS}/catalog", {"search": "f"}).data["results"] == []
    assert names(client.get(f"{INPUTS}/catalog", {"search": "FUNGICIDA"})) == ["Fungicida"]
    assert client.get(f"{INPUTS}/catalog").status_code == 400


def test_the_catalog_search_is_for_those_who_register_entries(auth_client, stores):
    viewer = make_delegate(
        stores.producer, ["inputs.view_agriculturalinput"], farm=stores.esperanza
    )

    response = auth_client(viewer).get(f"{INPUTS}/catalog", {"search": "fungi"})

    assert response.status_code == 403


def test_an_entry_brings_an_input_of_another_farm_into_the_farm(auth_client, stores):
    client = auth_client(stores.foreman)

    response = client.post(MOVEMENTS, entry(stores.fungicide, stores.esperanza), format="json")

    assert response.status_code == 201
    assert "Fungicida" in names(client.get(INPUTS))
    # Lo que hay en la otra finca no cambia.
    assert InputStock.objects.get(input=stores.fungicide, farm=stores.recreo).quantity == 8


def test_an_employee_registers_movements_only_in_its_farm(auth_client, stores):
    response = auth_client(stores.foreman).post(
        MOVEMENTS, entry(stores.urea, stores.recreo), format="json"
    )

    assert response.status_code == 404
    assert InputStock.objects.get(input=stores.urea, farm=stores.recreo).quantity == 20


def test_an_employee_cannot_count_an_input_that_is_not_in_its_farm(auth_client, stores):
    body = {
        "input_id": str(stores.fungicide.pk),
        "farm_id": str(stores.esperanza.pk),
        "kind": "count",
        "counted_quantity": "3",
        "occurred_on": str(timezone.localdate()),
    }

    response = auth_client(stores.foreman).post(MOVEMENTS, body, format="json")

    assert response.status_code == 404
    assert not InputStock.objects.filter(input=stores.fungicide, farm=stores.esperanza).exists()


# --- Editar ---


def test_an_employee_edits_an_input_that_is_only_in_its_farm(auth_client, stores):
    response = auth_client(stores.foreman).patch(
        f"{INPUTS}/{stores.lime.pk}",
        {"name": "Cal agrícola", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == "Cal agrícola"


@pytest.mark.parametrize("change", [{"name": "Urea 46"}, {"is_active": False}])
def test_an_input_shared_with_another_farm_is_changed_only_by_the_producer(
    auth_client, stores, change
):
    body = {**change, "expected_version": 1}
    url = f"{INPUTS}/{stores.urea.pk}"

    by_employee = auth_client(stores.foreman).patch(url, body, format="json")

    assert (by_employee.status_code, by_employee.data["code"]) == (409, "input_shared")
    assert auth_client(stores.owner).patch(url, body, format="json").status_code == 200


def test_an_employee_never_changes_the_unit(auth_client, stores):
    client = auth_client(stores.foreman)
    # Recién registrado y sin movimientos: la regla de la unidad bloqueada todavía no aplica.
    created = client.post(INPUTS, input_data(name="Cobre", unit="kg"), format="json").data
    url = f"{INPUTS}/{created['id']}"
    body = {"unit": "g", "expected_version": 1}

    by_employee = client.patch(url, body, format="json")

    assert by_employee.status_code == 403
    assert by_employee.data["code"] == "permission_denied"
    assert "unit" in by_employee.data["fields"]
    assert AgriculturalInput.objects.get(pk=created["id"]).unit == "kg"
    assert auth_client(stores.owner).patch(url, body, format="json").status_code == 200


def test_an_employee_does_not_reach_an_input_of_another_farm_to_edit_it(auth_client, stores):
    response = auth_client(stores.foreman).patch(
        f"{INPUTS}/{stores.fungicide.pk}", {"name": "Otro", "expected_version": 1}, format="json"
    )

    assert response.status_code == 404


# --- Eliminar ---


def test_an_input_without_movements_is_deleted_with_its_place_in_the_farm(auth_client, stores):
    deleter = make_delegate(
        stores.producer,
        [
            "inputs.view_agriculturalinput",
            "inputs.add_agriculturalinput",
            "inputs.delete_agriculturalinput",
        ],
        farm=stores.esperanza,
    )
    client = auth_client(deleter)
    created = client.post(INPUTS, input_data(name="Cobre"), format="json").data

    response = client.delete(f"{INPUTS}/{created['id']}?expected_version=1")

    assert response.status_code == 204
    assert not AgriculturalInput.objects.filter(pk=created["id"]).exists()
    assert not InputStock.objects.filter(input_id=created["id"]).exists()


def test_a_farm_whose_inputs_have_no_movements_can_still_be_deleted(auth_client, stores):
    farm = FarmFactory(producer=stores.producer, name="Recién creada")
    item = AgriculturalInputFactory(producer=stores.producer, name="Cobre")
    InputStock.objects.create(input=item, farm=farm)

    response = auth_client(stores.owner).delete(f"/api/farms/{farm.pk}?expected_version=1")

    assert response.status_code == 204
    assert not Farm.objects.filter(pk=farm.pk).exists()
    assert AgriculturalInput.objects.filter(pk=item.pk).exists()


# --- Un empleado de varias fincas ---


def test_an_employee_of_two_farms_sees_the_inputs_of_both_once(auth_client, stores):
    both = grant_role(
        UserFactory(producer=stores.producer, farms=[stores.esperanza, stores.recreo]),
        get_system_role(FOREMAN),
    )

    # La Urea está en las dos fincas y sale una sola vez.
    assert names(auth_client(both).get(INPUTS)) == ["Cal", "Fungicida", "Urea"]


def test_an_employee_of_two_farms_says_where_a_new_input_goes(auth_client, stores):
    both = grant_role(
        UserFactory(producer=stores.producer, farms=[stores.esperanza, stores.recreo]),
        get_system_role(FOREMAN),
    )
    client = auth_client(both)

    unsaid = client.post(INPUTS, input_data(name="Cobre"), format="json")
    said = client.post(
        INPUTS, input_data(name="Cobre", farm_id=str(stores.recreo.pk)), format="json"
    )

    assert unsaid.status_code == 400
    assert "farm_id" in unsaid.data["fields"]
    assert said.status_code == 201
    assert InputStock.objects.filter(input_id=said.data["id"], farm=stores.recreo).exists()


def test_a_new_input_cannot_go_to_a_farm_the_employee_does_not_work_in(auth_client, stores):
    response = auth_client(stores.foreman).post(
        INPUTS, input_data(name="Cobre", farm_id=str(stores.recreo.pk)), format="json"
    )

    assert response.status_code == 400
    assert "farm_id" in response.data["fields"]


def test_the_inputs_of_one_farm_are_those_that_are_in_it(auth_client, stores):
    # Lo que se ofrece al registrar una labor en una parcela de esa finca.
    both = grant_role(
        UserFactory(producer=stores.producer, farms=[stores.esperanza, stores.recreo]),
        get_system_role(FOREMAN),
    )
    client = auth_client(both)

    assert names(client.get(INPUTS, {"farm": str(stores.esperanza.pk)})) == ["Cal", "Urea"]
    assert names(client.get(INPUTS, {"farm": str(stores.recreo.pk)})) == ["Fungicida", "Urea"]


def test_the_inputs_of_a_farm_outside_the_scope_are_none(auth_client, stores):
    response = auth_client(stores.foreman).get(INPUTS, {"farm": str(stores.recreo.pk)})

    assert names(response) == []
