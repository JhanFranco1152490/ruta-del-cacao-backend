"""Eliminar un lote conformado por error: solo Generado, y el código no se reutiliza."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.harvests.models import Harvest
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.models import Lot, LotAuditEvent, LotCodeSequence
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

DAY = date(2026, 10, 14)


class Estate:
    def __init__(self):
        self.producer = ProducerFactory(member_code="PROD-000123")
        self.farm = FarmFactory(producer=self.producer, number=2)
        self.plot = characterized_plot(farm=self.farm, number=5, area_hectares=Decimal("5.00"))
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm), get_system_role(FOREMAN)
        )

    def conform(self, client, day=DAY):
        harvest = HarvestFactory(plot=self.plot, harvest_date=day)
        response = client.post("/api/lots", {"harvest_id": str(harvest.pk)}, format="json")
        return harvest, response


@pytest.fixture
def estate():
    return Estate()


def delete(client, lot_id, version=1):
    query = "" if version is None else f"?expected_version={version}"
    return client.delete(f"/api/lots/{lot_id}{query}")


def test_the_producer_deletes_a_generated_lot_and_the_harvest_is_free_again(auth_client, estate):
    owner = auth_client(estate.owner)
    harvest, created = estate.conform(owner)

    response = delete(owner, created.data["id"])

    assert response.status_code == 204
    assert not Lot.objects.exists()
    assert Harvest.objects.filter(pk=harvest.pk).exists()
    corrected = owner.patch(
        f"/api/harvests/{harvest.pk}",
        {"expected_version": 1, "green_weight_kg": "99.0"},
        format="json",
    )
    assert corrected.status_code == 200


def test_the_deletion_leaves_the_code_and_the_origin_in_the_history(auth_client, estate):
    owner = auth_client(estate.owner)
    harvest, created = estate.conform(owner)

    delete(owner, created.data["id"])

    deleted = LotAuditEvent.objects.get(action="deleted")
    assert deleted.lot_id is None
    assert deleted.code == "000123-F02-P05-261014-1"
    assert deleted.harvest_ref == harvest.pk
    assert deleted.actor == estate.owner
    assert LotAuditEvent.objects.filter(action="created", lot_ref=deleted.lot_ref).exists()


def test_the_consecutive_of_a_deleted_lot_is_not_reused(auth_client, estate):
    owner = auth_client(estate.owner)
    _, first = estate.conform(owner)
    _, second = estate.conform(owner)
    assert second.data["code"].endswith("-261014-2")

    delete(owner, second.data["id"])
    _, third = estate.conform(owner)

    assert first.data["code"].endswith("-261014-1")
    assert third.data["code"].endswith("-261014-3")
    assert LotCodeSequence.objects.get().last_value == 3


@pytest.mark.parametrize(
    "status",
    [LotStatus.FERMENTING, LotStatus.FERMENTED, LotStatus.DRYING, LotStatus.DRIED],
)
def test_a_lot_beyond_generated_is_not_deleted(auth_client, estate, status):
    owner = auth_client(estate.owner)
    _, created = estate.conform(owner)
    Lot.objects.update(status=status)

    response = delete(owner, created.data["id"])

    assert response.status_code == 409
    assert response.data["code"] == "lot_invalid_status"
    assert response.data["current_status"] == status.value
    assert Lot.objects.exists()


def test_an_outdated_version_returns_the_current_lot(auth_client, estate):
    owner = auth_client(estate.owner)
    _, created = estate.conform(owner)
    Lot.objects.update(version=2)

    response = delete(owner, created.data["id"], version=1)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2
    assert Lot.objects.exists()


def test_the_version_is_required(auth_client, estate):
    owner = auth_client(estate.owner)
    _, created = estate.conform(owner)

    response = delete(owner, created.data["id"], version=None)

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_a_foreman_cannot_delete(auth_client, estate):
    foreman = auth_client(estate.foreman)
    _, created = estate.conform(foreman)

    assert delete(foreman, created.data["id"]).status_code == 403
    assert Lot.objects.exists()


def test_what_is_out_of_reach_or_unknown_does_not_exist(auth_client, estate):
    _, created = estate.conform(auth_client(estate.owner))
    stranger = auth_client(make_producer_owner(ProducerFactory()))

    assert delete(stranger, created.data["id"]).status_code == 404
    assert delete(auth_client(estate.owner), uuid.uuid4()).status_code == 404
    assert Lot.objects.exists()


def test_the_technical_account_can_delete(auth_client, estate):
    _, created = estate.conform(auth_client(estate.owner))

    assert (
        delete(auth_client(UserFactory(is_superuser=True)), created.data["id"]).status_code == 204
    )
