"""Conformar un lote: el código que le asigna el servidor y las reglas de su cosecha."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.models import Lot, LotAuditEvent, LotCodeSequence
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

DAY = date(2026, 10, 14)


class Estate:
    """El productor PROD-000123, su finca F02 con la parcela P05 y un capataz en ella."""

    def __init__(self, member_code="PROD-000123"):
        self.producer = ProducerFactory(member_code=member_code)
        self.farm = FarmFactory(producer=self.producer, number=2)
        self.plot = characterized_plot(farm=self.farm, number=5, area_hectares=Decimal("5.00"))
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm), get_system_role(FOREMAN)
        )

    def harvest(self, day=DAY, **fields):
        return HarvestFactory(plot=self.plot, harvest_date=day, **fields)


@pytest.fixture
def estate():
    return Estate()


@pytest.fixture
def client(auth_client, estate):
    return auth_client(estate.foreman)


def create(client, harvest, **fields):
    return client.post("/api/lots", {"harvest_id": str(harvest.pk), **fields}, format="json")


def test_the_lot_gets_the_code_that_says_its_origin(client, estate):
    harvest = estate.harvest()

    response = create(client, harvest, id=str(uuid.uuid4()))

    assert response.status_code == 201
    assert response.data["code"] == "000123-F02-P05-261014-1"
    assert response.data["status"] == "generated"
    lot = Lot.objects.get()
    assert response["Location"] == f"/api/lots/{lot.pk}"
    assert lot.created_by == estate.foreman


def test_the_response_has_the_contract_shape(client, estate):
    harvest = estate.harvest()

    body = create(client, harvest).json()

    assert body["producer"] == {"id": str(estate.producer.pk), "member_code": "PROD-000123"}
    assert body["green_weight_kg"] == "120.5"
    assert body["created_by"]["id"] == str(estate.foreman.pk)
    assert body["harvest"]["id"] == str(harvest.pk)
    assert body["harvest"]["plot"]["code"] == "P05"
    assert body["harvest"]["plot"]["farm"]["code"] == "F02"
    assert "lot" not in body["harvest"]
    assert body["version"] == 1


def test_the_event_of_creation_keeps_the_code(client, estate):
    create(client, estate.harvest())

    event = LotAuditEvent.objects.get()
    assert (event.action, event.actor, event.code) == (
        "created",
        estate.foreman,
        "000123-F02-P05-261014-1",
    )
    assert event.version == 1


def test_a_second_harvest_of_the_same_plot_and_day_gets_the_next_consecutive(client, estate):
    first = create(client, estate.harvest())
    second = create(client, estate.harvest())

    assert first.data["code"].endswith("-261014-1")
    assert second.data["code"].endswith("-261014-2")


def test_another_day_or_another_plot_starts_again_at_one(client, estate):
    create(client, estate.harvest())
    other_day = create(client, estate.harvest(day=date(2026, 10, 15)))
    other_plot = characterized_plot(farm=estate.farm, number=6)
    elsewhere = create(client, HarvestFactory(plot=other_plot, harvest_date=DAY))

    assert other_day.data["code"].endswith("-261015-1")
    assert elsewhere.data["code"] == "000123-F02-P06-261014-1"


def test_a_harvest_that_already_forms_a_lot_is_refused_with_that_lot(client, estate):
    harvest = estate.harvest()
    first = create(client, harvest)

    response = create(client, harvest, id=str(uuid.uuid4()))

    assert response.status_code == 409
    assert response.data["code"] == "harvest_already_in_lot"
    assert response.data["current"]["id"] == first.data["id"]
    assert Lot.objects.count() == 1


def test_a_refused_creation_does_not_use_a_consecutive(client, estate):
    harvest = estate.harvest()
    create(client, harvest)
    create(client, harvest, id=str(uuid.uuid4()))

    third = create(client, estate.harvest())

    assert third.data["code"].endswith("-261014-2")
    assert LotCodeSequence.objects.get().last_value == 2


def test_resending_the_same_lot_returns_200_without_creating_another(client, estate):
    harvest = estate.harvest()
    lot_id = str(uuid.uuid4())
    first = create(client, harvest, id=lot_id)

    second = create(client, harvest, id=lot_id)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.data["code"] == first.data["code"]
    assert Lot.objects.count() == 1
    assert LotCodeSequence.objects.get().last_value == 1


def test_the_same_id_for_another_harvest_is_a_conflict(client, estate):
    lot_id = str(uuid.uuid4())
    create(client, estate.harvest(), id=lot_id)

    response = create(client, estate.harvest(), id=lot_id)

    assert response.status_code == 409
    assert response.data["code"] == "lot_id_conflict"
    assert "current" not in response.data


def test_the_id_of_another_producer_is_a_conflict_without_its_data(auth_client, estate):
    lot_id = str(uuid.uuid4())
    create(auth_client(estate.foreman), estate.harvest(), id=lot_id)
    other = Estate(member_code="PROD-000124")

    response = create(auth_client(other.foreman), other.harvest(), id=lot_id)

    assert response.status_code == 409
    assert response.data["code"] == "lot_id_conflict"
    assert Lot.objects.count() == 1


def test_a_harvest_out_of_reach_does_not_exist(auth_client, estate):
    foreman = auth_client(estate.foreman)
    other_farm_harvest = HarvestFactory(
        plot=characterized_plot(farm=FarmFactory(producer=estate.producer))
    )

    assert create(foreman, other_farm_harvest).status_code == 404
    assert create(foreman, HarvestFactory()).status_code == 404
    assert create(foreman, type("H", (), {"pk": uuid.uuid4()})).status_code == 404
    assert not Lot.objects.exists()


def test_the_harvest_is_required(client):
    response = client.post("/api/lots", {}, format="json")

    assert response.status_code == 400
    assert "harvest_id" in response.data["fields"]


def test_an_inactive_plot_and_farm_still_form_the_lot_of_a_recorded_harvest(client, estate):
    harvest = estate.harvest()
    estate.plot.is_active = False
    estate.plot.save()
    estate.farm.is_active = False
    estate.farm.save()

    assert create(client, harvest).status_code == 201


def test_the_producer_and_the_technical_account_can_conform_lots(auth_client, estate):
    assert create(auth_client(estate.owner), estate.harvest()).status_code == 201
    assert create(auth_client(UserFactory(is_superuser=True)), estate.harvest()).status_code == 201


def test_without_the_permission_or_the_session_it_is_refused(
    auth_client, anonymous_client, estate
):
    viewer = make_delegate(estate.producer, ["lots.view_lot"], farm=estate.farm)
    harvest = estate.harvest()

    assert create(auth_client(viewer), harvest).status_code == 403
    assert create(auth_client(make_administrator()), harvest).status_code == 403
    assert create(anonymous_client, harvest).status_code in (401, 403)


def test_a_conformed_lot_freezes_its_harvest(auth_client, estate):
    harvest = estate.harvest()
    create(auth_client(estate.foreman), harvest)
    owner = auth_client(estate.owner)

    edited = owner.patch(
        f"/api/harvests/{harvest.pk}",
        {"expected_version": 1, "green_weight_kg": "99.0"},
        format="json",
    )
    deleted = owner.delete(f"/api/harvests/{harvest.pk}?expected_version=1")

    assert (edited.status_code, edited.data["code"]) == (409, "harvest_in_lot")
    assert (deleted.status_code, deleted.data["code"]) == (409, "harvest_in_lot")
    harvest.refresh_from_db()
    assert (harvest.green_weight_kg, harvest.version) == (Decimal("120.5"), 1)


def test_the_harvest_says_its_lot(auth_client, estate):
    harvest = estate.harvest()
    created = create(auth_client(estate.foreman), harvest)

    listed = auth_client(estate.owner).get(
        "/api/harvests", {"from": "2026-10-01", "to": "2026-10-31"}
    )

    assert listed.data["results"][0]["lot"] == {
        "id": uuid.UUID(created.data["id"]),
        "code": "000123-F02-P05-261014-1",
        "status": "generated",
    }
