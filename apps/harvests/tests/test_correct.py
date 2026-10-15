"""Corregir y eliminar una cosecha que todavía no forma un lote."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.crops.tests.factories import CacaoVarietyFactory, PlotPlantingFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.models import Harvest, HarvestAuditEvent
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: TODAY)


class Setup:
    def __init__(self):
        self.producer = ProducerFactory()
        self.farm = FarmFactory(producer=self.producer)
        self.variety = CacaoVarietyFactory()
        self.plot = characterized_plot(
            variety=self.variety,
            planting_date=date(2019, 5, 1),
            farm=self.farm,
            area_hectares=Decimal("2.00"),
        )
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm), get_system_role(FOREMAN)
        )
        self.harvest = HarvestFactory(
            plot=self.plot,
            variety=self.variety,
            collector=self.foreman,
            harvest_date=date(2026, 10, 10),
            green_weight_kg=Decimal("100.0"),
        )


@pytest.fixture
def setup():
    return Setup()


@pytest.fixture
def client(auth_client, setup):
    return auth_client(setup.foreman)


def patch(client, harvest, **fields):
    body = {"expected_version": harvest.version, **fields}
    return client.patch(f"/api/harvests/{harvest.pk}", body, format="json")


def test_corrects_the_weight_and_leaves_the_old_value_in_the_history(client, setup):
    response = patch(client, setup.harvest, green_weight_kg="105.5")

    assert response.status_code == 200
    assert (response.data["green_weight_kg"], response.data["version"]) == ("105.5", 2)
    event = HarvestAuditEvent.objects.get(harvest=setup.harvest, action="updated")
    assert event.actor == setup.foreman
    assert event.version == 2
    assert event.changes == {"green_weight_kg": {"before": "100.0", "after": "105.5"}}


def test_corrects_the_date(client, setup):
    response = patch(client, setup.harvest, harvest_date="2026-10-12")

    assert response.data["harvest_date"] == "2026-10-12"


def test_the_corrected_values_are_validated_like_the_registration(client, setup):
    assert patch(client, setup.harvest, green_weight_kg="0").status_code == 400
    assert patch(client, setup.harvest, green_weight_kg="4000.1").status_code == 400
    assert patch(client, setup.harvest, harvest_date="2026-10-15").status_code == 400
    assert patch(client, setup.harvest, harvest_date="2019-04-30").status_code == 400
    setup.harvest.refresh_from_db()
    assert setup.harvest.version == 1


def test_changing_the_variety_takes_the_current_version_of_the_characterization(client, setup):
    other = CacaoVarietyFactory()
    PlotPlantingFactory(
        characterization=setup.plot.characterization,
        variety=other,
        planting_date=date(2020, 1, 1),
    )
    characterization = setup.plot.characterization
    characterization.version = 5
    characterization.save()

    response = patch(client, setup.harvest, variety_id=str(other.pk))

    assert response.status_code == 200
    assert response.data["variety"]["id"] == str(other.pk)
    assert response.data["characterization_version"] == 5


def test_correcting_only_the_weight_keeps_the_version_of_the_characterization(client, setup):
    characterization = setup.plot.characterization
    characterization.version = 5
    characterization.save()

    response = patch(client, setup.harvest, green_weight_kg="90.0")

    assert response.data["characterization_version"] == 1


def test_a_variety_outside_the_characterization_is_refused(client, setup):
    response = patch(client, setup.harvest, variety_id=str(CacaoVarietyFactory().pk))

    assert response.status_code == 422
    assert response.data["code"] == "variety_not_in_plot"


def test_the_new_date_is_checked_against_the_new_variety(client, setup):
    other = CacaoVarietyFactory()
    PlotPlantingFactory(
        characterization=setup.plot.characterization,
        variety=other,
        planting_date=date(2026, 9, 1),
    )

    response = patch(client, setup.harvest, variety_id=str(other.pk), harvest_date="2026-08-31")

    assert response.status_code == 400
    assert "harvest_date" in response.data["fields"]


def test_changes_the_collector_only_to_a_valid_one(client, setup):
    colleague = make_delegate(setup.producer, ["harvests.add_harvest"], farm=setup.farm)
    elsewhere = make_delegate(
        setup.producer, ["harvests.add_harvest"], farm=FarmFactory(producer=setup.producer)
    )

    ok = patch(client, setup.harvest, collector_id=str(colleague.pk))
    refused = patch(
        client, Harvest.objects.get(pk=setup.harvest.pk), collector_id=str(elsewhere.pk)
    )

    assert str(ok.data["collector"]["id"]) == str(colleague.pk)
    assert (refused.status_code, refused.data["code"]) == (422, "collector_not_available")


def test_the_unchanged_fields_are_not_revalidated(auth_client, setup):
    # La variedad desapareció de la ficha y el recolector ya no trabaja en la finca: el peso se
    # corrige igual.
    setup.plot.characterization.plantings.all().delete()
    setup.foreman.farms.clear()

    response = patch(auth_client(setup.owner), setup.harvest, green_weight_kg="90.0")

    assert response.status_code == 200


def test_a_date_correction_without_the_planting_only_checks_it_is_not_future(client, setup):
    setup.plot.characterization.plantings.all().delete()

    assert patch(client, setup.harvest, harvest_date="2018-01-01").status_code == 200
    assert (
        patch(
            client, Harvest.objects.get(pk=setup.harvest.pk), harvest_date="2026-10-15"
        ).status_code
        == 400
    )


def test_no_real_change_neither_raises_the_version_nor_leaves_history(client, setup):
    response = patch(client, setup.harvest, green_weight_kg="100.0", harvest_date="2026-10-10")

    assert response.status_code == 200
    assert response.data["version"] == 1
    assert HarvestAuditEvent.objects.filter(action="updated").count() == 0


def test_an_outdated_version_returns_the_current_harvest(client, setup):
    patch(client, setup.harvest, green_weight_kg="101.0")

    response = patch(client, setup.harvest, green_weight_kg="102.0")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["green_weight_kg"] == "101.0"
    assert response.data["current"]["version"] == 2


def test_resending_an_applied_correction_is_a_success(client, setup):
    patch(client, setup.harvest, green_weight_kg="101.0")

    response = patch(client, setup.harvest, green_weight_kg="101.0")

    assert response.status_code == 200
    assert response.data["version"] == 2


def test_the_plot_cannot_be_changed(client, setup):
    other = characterized_plot(farm=setup.farm)

    response = patch(client, setup.harvest, plot_id=str(other.pk))

    assert response.status_code == 400
    assert "plot_id" in response.data["fields"]


def test_an_update_needs_the_version_and_a_change(client, setup):
    assert (
        client.patch(
            f"/api/harvests/{setup.harvest.pk}", {"green_weight_kg": "9.0"}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/harvests/{setup.harvest.pk}", {"expected_version": 1}, format="json"
        ).status_code
        == 400
    )


def test_nothing_out_of_reach_can_be_corrected(auth_client, setup):
    stranger = HarvestFactory()
    other_farm = HarvestFactory(plot=characterized_plot(farm=FarmFactory(producer=setup.producer)))
    foreman = auth_client(setup.foreman)

    assert patch(foreman, stranger, green_weight_kg="5.0").status_code == 404
    assert patch(foreman, other_farm, green_weight_kg="5.0").status_code == 404


def test_without_the_permission_it_is_forbidden(auth_client, setup):
    viewer = make_delegate(setup.producer, ["harvests.view_harvest"], farm=setup.farm)

    assert patch(auth_client(viewer), setup.harvest, green_weight_kg="5.0").status_code == 403


# --- Eliminar -----------------------------------------------------------------------------


def delete(client, harvest, version=None):
    query = "" if version is None else f"?expected_version={version}"
    return client.delete(f"/api/harvests/{harvest.pk}{query}")


def test_the_producer_deletes_a_harvest_and_the_history_keeps_what_it_said(auth_client, setup):
    harvest_id = setup.harvest.pk

    response = delete(auth_client(setup.owner), setup.harvest, 1)

    assert response.status_code == 204
    assert not Harvest.objects.filter(pk=harvest_id).exists()
    events = HarvestAuditEvent.objects.filter(harvest_ref=harvest_id).order_by("occurred_at")
    assert [event.action for event in events] == ["created", "deleted"] or events.count() == 1
    deleted = events.get(action="deleted")
    assert deleted.harvest_id is None
    assert deleted.plot_ref == setup.plot.pk
    assert deleted.changes["green_weight_kg"] == {"before": "100.0", "after": None}


def test_a_foreman_cannot_delete(client, setup):
    assert delete(client, setup.harvest, 1).status_code == 403
    assert Harvest.objects.filter(pk=setup.harvest.pk).exists()


def test_deleting_needs_the_expected_version(auth_client, setup):
    response = delete(auth_client(setup.owner), setup.harvest)

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_deleting_an_outdated_version_returns_the_current_harvest(auth_client, setup):
    patch(auth_client(setup.owner), setup.harvest, green_weight_kg="101.0")

    response = delete(auth_client(setup.owner), setup.harvest, 1)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2


def test_deleting_what_is_out_of_reach_does_not_exist(auth_client, setup):
    assert (
        delete(auth_client(make_producer_owner(ProducerFactory())), setup.harvest, 1).status_code
        == 404
    )
    assert delete(auth_client(UserFactory(is_superuser=True)), setup.harvest, 1).status_code == 204


def test_an_unknown_harvest_does_not_exist(auth_client, setup):
    response = auth_client(setup.owner).delete(f"/api/harvests/{uuid.uuid4()}?expected_version=1")

    assert response.status_code == 404
