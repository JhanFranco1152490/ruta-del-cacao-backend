import uuid

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import enable_association_access, make_administrator
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.farms.tests.test_api import FARM_PERMISSIONS, VALID_DATA
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    return make_administrator()


@pytest.fixture
def client(auth_client, admin):
    return auth_client(admin)


@pytest.fixture
def open_producer():
    """Productor que encendió el interruptor: la asociación puede gestionar sus fincas."""
    producer = ProducerFactory()
    enable_association_access(producer)
    return producer


@pytest.fixture
def closed_producer():
    """Productor con el interruptor apagado (el valor por defecto)."""
    return ProducerFactory()


def create_for(client, producer, **overrides):
    return client.post(
        "/api/farms", {**VALID_DATA, "producer_id": str(producer.id), **overrides}, format="json"
    )


# --- Crear -------------------------------------------------------------------------------


def test_the_association_creates_a_farm_for_a_producer_with_access(client, admin, open_producer):
    response = create_for(client, open_producer)

    assert response.status_code == 201
    assert response.data["producer_id"] == str(open_producer.id)
    farm = Farm.objects.get(pk=response.data["id"])
    assert farm.producer == open_producer
    assert FarmAuditEvent.objects.get(farm=farm).actor == admin


def test_the_association_cannot_create_for_a_producer_without_access(client, closed_producer):
    response = create_for(client, closed_producer)

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert not Farm.objects.exists()


def test_the_association_must_say_for_which_producer_it_creates(client):
    response = client.post("/api/farms", VALID_DATA, format="json")

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_the_association_cannot_create_for_an_unknown_producer(client):
    response = client.post(
        "/api/farms", {**VALID_DATA, "producer_id": str(uuid.uuid4())}, format="json"
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_a_resent_farm_from_the_association_is_not_duplicated(client, open_producer):
    data = {"id": str(uuid.uuid4())}
    first = create_for(client, open_producer, **data)

    again = create_for(client, open_producer, **data)
    edited = create_for(client, open_producer, **data, altitude_masl=1000)

    assert (first.status_code, again.status_code) == (201, 200)
    assert Farm.objects.count() == 1
    assert edited.status_code == 409
    assert edited.data["code"] == "farm_id_conflict"
    assert edited.data["current"]["id"] == data["id"]


def test_an_account_outside_the_association_and_without_producer_cannot_create(auth_client):
    # Tiene los permisos asignados a mano, pero no es de la asociación ni de un productor.
    user = UserFactory(permissions=FARM_PERMISSIONS)
    client = auth_client(user)

    created = client.post(
        "/api/farms", {**VALID_DATA, "producer_id": str(ProducerFactory().id)}, format="json"
    )
    listed = client.get("/api/farms")

    assert created.status_code == 403
    assert listed.data["count"] == 0


# --- Editar ------------------------------------------------------------------------------


def test_the_association_edits_and_deactivates_a_farm_with_access(client, open_producer):
    farm = FarmFactory(producer=open_producer)

    renamed = client.patch(
        f"/api/farms/{farm.id}", {"name": "Nuevo nombre", "expected_version": 1}, format="json"
    )
    deactivated = client.patch(
        f"/api/farms/{farm.id}", {"is_active": False, "expected_version": 2}, format="json"
    )

    assert (renamed.status_code, renamed.data["name"]) == (200, "Nuevo nombre")
    assert (deactivated.status_code, deactivated.data["is_active"]) == (200, False)


def test_the_association_reads_but_cannot_edit_a_farm_without_access(client, closed_producer):
    farm = FarmFactory(producer=closed_producer, name="Sin acceso")

    read = client.get(f"/api/farms/{farm.id}")
    edit = client.patch(
        f"/api/farms/{farm.id}", {"name": "Cambiado", "expected_version": 1}, format="json"
    )

    assert read.status_code == 200
    assert edit.status_code == 403
    assert edit.data["code"] == "permission_denied"
    farm.refresh_from_db()
    assert (farm.name, farm.version) == ("Sin acceso", 1)


# --- Listar ------------------------------------------------------------------------------


def test_the_association_filters_the_list_by_producer(client, open_producer, closed_producer):
    own = FarmFactory(producer=open_producer)
    FarmFactory(producer=closed_producer)

    filtered = client.get("/api/farms", {"producer": str(open_producer.id)})
    everything = client.get("/api/farms")

    assert [farm["id"] for farm in filtered.data["results"]] == [str(own.id)]
    assert everything.data["count"] == 2
