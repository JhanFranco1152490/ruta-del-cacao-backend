"""Registrar una cosecha: la ficha de la parcela, el recolector, la fecha y el peso."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.crops.tests.factories import (
    CacaoVarietyFactory,
    PlotCharacterizationFactory,
    PlotPlantingFactory,
)
from apps.farms.tests.factories import FarmFactory
from apps.harvests.models import Harvest, HarvestAuditEvent
from apps.harvests.tests.factories import characterized_plot
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: TODAY)


class Field:
    """Un productor con su finca, una parcela con ficha de una variedad y un capataz."""

    def __init__(self, variety=None):
        self.producer = ProducerFactory()
        self.farm = FarmFactory(producer=self.producer)
        self.variety = variety or CacaoVarietyFactory(name="CCN-51")
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

    def body(self, **overrides):
        data = {
            "plot_id": str(self.plot.pk),
            "harvest_date": "2026-10-14",
            "green_weight_kg": "120.5",
            "variety_id": str(self.variety.pk),
            "collector_id": str(self.foreman.pk),
        }
        data.update(overrides)
        return data


@pytest.fixture
def field():
    return Field()


@pytest.fixture
def client(auth_client, field):
    return auth_client(field.foreman)


def register(client, field, **overrides):
    return client.post("/api/harvests", field.body(**overrides), format="json")


def test_registers_a_harvest_with_the_version_of_the_characterization(client, field):
    version_before = field.plot.characterization.version

    response = register(client, field, id=str(uuid.uuid4()))

    assert response.status_code == 201
    harvest = Harvest.objects.get()
    assert response["Location"] == f"/api/harvests/{harvest.pk}"
    assert harvest.plot_id == field.plot.pk
    assert harvest.characterization_version == version_before
    assert harvest.registered_by == field.foreman
    assert harvest.green_weight_kg == Decimal("120.5")
    event = HarvestAuditEvent.objects.get(harvest=harvest)
    assert (event.action, event.actor, event.version) == ("created", field.foreman, 1)
    assert event.changes["green_weight_kg"] == {"before": None, "after": "120.5"}


def test_the_response_has_the_contract_shape(client, field):
    response = register(client, field)

    body = response.json()
    assert body["plot"] == {
        "id": str(field.plot.pk),
        "code": "P01",
        "name": field.plot.name,
        "is_active": True,
        "farm": {
            "id": str(field.farm.pk),
            "code": "F01",
            "name": field.farm.name,
            "is_active": True,
        },
    }
    assert body["producer_id"] == str(field.producer.pk)
    assert body["variety"] == {"id": str(field.variety.pk), "name": "CCN-51", "is_active": True}
    assert body["collector"]["id"] == str(field.foreman.pk)
    assert body["registered_by"]["id"] == str(field.foreman.pk)
    assert body["green_weight_kg"] == "120.5"
    assert (body["lot"], body["version"]) == (None, 1)


def test_the_plot_characterization_version_follows_the_current_one(client, field):
    characterization = field.plot.characterization
    characterization.version = 4
    characterization.save()

    register(client, field)

    assert Harvest.objects.get().characterization_version == 4


@pytest.mark.parametrize(
    "missing", ["plot_id", "harvest_date", "green_weight_kg", "variety_id", "collector_id"]
)
def test_every_required_field_is_validated(client, field, missing):
    data = field.body()
    del data[missing]

    response = client.post("/api/harvests", data, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert missing in response.data["fields"]
    assert not Harvest.objects.exists()


@pytest.mark.parametrize("weight", ["0", "0.0", "-3"])
def test_the_weight_must_be_greater_than_zero(client, field, weight):
    response = register(client, field, green_weight_kg=weight)

    assert response.status_code == 400
    assert response.data["fields"]["green_weight_kg"] == ["El peso debe ser mayor a 0."]


def test_the_weight_allows_a_single_decimal(client, field):
    response = register(client, field, green_weight_kg="120.55")

    assert response.status_code == 400
    assert "green_weight_kg" in response.data["fields"]


def test_the_weight_is_capped_at_two_thousand_kilos_per_declared_hectare(client, field):
    assert register(client, field, green_weight_kg="4000.0").status_code == 201

    response = register(client, field, green_weight_kg="4000.1")

    assert response.status_code == 400
    assert response.data["fields"]["green_weight_kg"] == [
        "El peso supera lo que puede dar una parcela de 2 ha en una recolección (4000 kg). "
        "Revisa la cifra."
    ]


def test_a_future_date_is_refused(client, field):
    response = register(client, field, harvest_date="2026-10-15")

    assert response.status_code == 400
    assert response.data["fields"]["harvest_date"] == ["La fecha no puede ser futura."]


def test_the_date_cannot_precede_the_planting_of_the_variety(client, field):
    response = register(client, field, harvest_date="2019-04-30")

    assert response.status_code == 400
    assert response.data["fields"]["harvest_date"] == [
        "La fecha es anterior a la siembra de CCN-51 en esta parcela (mayo de 2019)."
    ]


def test_the_month_of_the_planting_is_accepted(client, field):
    # La siembra se guarda el día 1 de su mes.
    assert register(client, field, harvest_date="2019-05-01").status_code == 201


def test_the_oldest_planting_of_the_variety_sets_the_earliest_date(client, field):
    PlotPlantingFactory(
        characterization=field.plot.characterization,
        variety=field.variety,
        planting_date=date(2022, 1, 1),
    )

    assert register(client, field, harvest_date="2019-06-10").status_code == 201


def test_the_date_is_checked_against_the_planting_of_the_chosen_variety(client, field):
    other = CacaoVarietyFactory(name="ICS-95")
    PlotPlantingFactory(
        characterization=field.plot.characterization,
        variety=other,
        planting_date=date(2024, 1, 1),
    )

    response = register(client, field, variety_id=str(other.pk), harvest_date="2023-12-31")

    assert response.status_code == 400
    assert "harvest_date" in response.data["fields"]


def test_a_plot_without_a_characterization_cannot_be_harvested(client, field):
    plot = PlotFactory(farm=field.farm)

    response = register(client, field, plot_id=str(plot.pk))

    assert response.status_code == 422
    assert response.data["code"] == "plot_not_characterized"


def test_a_characterization_without_plantings_cannot_be_harvested(client, field):
    plot = PlotFactory(farm=field.farm)
    PlotCharacterizationFactory(plot=plot)

    response = register(client, field, plot_id=str(plot.pk))

    assert response.status_code == 422
    assert response.data["code"] == "plot_not_characterized"


def test_a_variety_outside_the_characterization_is_refused(client, field):
    response = register(client, field, variety_id=str(CacaoVarietyFactory().pk))

    assert response.status_code == 422
    assert response.data["code"] == "variety_not_in_plot"


def test_an_unknown_variety_is_also_not_in_the_plot(client, field):
    response = register(client, field, variety_id=str(uuid.uuid4()))

    assert response.status_code == 422
    assert response.data["code"] == "variety_not_in_plot"


def test_a_collector_from_another_farm_is_refused(client, field):
    elsewhere = grant_role(
        UserFactory(producer=field.producer, farm=FarmFactory(producer=field.producer)),
        get_system_role(FOREMAN),
    )

    response = register(client, field, collector_id=str(elsewhere.pk))

    assert response.status_code == 422
    assert response.data["code"] == "collector_not_available"


def test_an_inactive_collector_is_refused(client, field):
    colleague = make_delegate(field.producer, ["harvests.add_harvest"], farm=field.farm)
    colleague.is_active = False
    colleague.save()

    response = register(client, field, collector_id=str(colleague.pk))

    assert response.status_code == 422
    assert response.data["code"] == "collector_not_available"


def test_a_collector_without_the_permission_is_refused(client, field):
    viewer = make_delegate(field.producer, ["harvests.view_harvest"], farm=field.farm)

    response = register(client, field, collector_id=str(viewer.pk))

    assert response.status_code == 422
    assert response.data["code"] == "collector_not_available"


def test_a_foreman_can_name_the_producer_only_if_it_is_themselves(client, field):
    response = register(client, field, collector_id=str(field.owner.pk))

    assert response.status_code == 422
    assert response.data["code"] == "collector_not_available"


def test_the_producer_can_name_itself_and_a_foreman(auth_client, field):
    owner_client = auth_client(field.owner)

    own = register(owner_client, field, collector_id=str(field.owner.pk))
    foreman = register(owner_client, field, collector_id=str(field.foreman.pk))

    assert (own.status_code, foreman.status_code) == (201, 201)


def test_an_inactive_plot_and_farm_still_receive_a_captured_harvest(client, field):
    field.plot.is_active = False
    field.plot.save()
    field.farm.is_active = False
    field.farm.save()

    assert register(client, field).status_code == 201


def test_a_plot_of_another_farm_does_not_exist_for_the_foreman(client, field):
    other_plot = characterized_plot(farm=FarmFactory(producer=field.producer))

    response = register(client, field, plot_id=str(other_plot.pk))

    assert response.status_code == 404
    assert not Harvest.objects.exists()


def test_a_plot_of_another_producer_does_not_exist(client, field):
    stranger_plot = characterized_plot()

    assert register(client, field, plot_id=str(stranger_plot.pk)).status_code == 404


def test_the_technical_account_registers_in_any_plot(auth_client, field):
    technical = UserFactory(is_superuser=True)

    response = register(auth_client(technical), field, collector_id=str(field.owner.pk))

    assert response.status_code == 201
    assert Harvest.objects.get().registered_by == technical


def test_the_association_cannot_register(auth_client, field):
    from apps.accounts.tests.role_helpers import make_administrator

    assert register(auth_client(make_administrator()), field).status_code == 403


def test_anonymous_cannot_register(anonymous_client, field):
    assert register(anonymous_client, field).status_code in (401, 403)


def test_a_resent_harvest_returns_200_without_duplicating(client, field):
    harvest_id = str(uuid.uuid4())
    first = register(client, field, id=harvest_id)

    second = register(client, field, id=harvest_id)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.data["id"] == harvest_id
    assert Harvest.objects.count() == 1
    assert HarvestAuditEvent.objects.count() == 1


def test_a_resent_harvest_is_not_validated_again(client, field):
    harvest_id = str(uuid.uuid4())
    register(client, field, id=harvest_id)
    field.plot.characterization.plantings.all().delete()

    assert register(client, field, id=harvest_id).status_code == 200


def test_the_same_id_with_other_data_is_a_conflict(client, field):
    harvest_id = str(uuid.uuid4())
    register(client, field, id=harvest_id)

    response = register(client, field, id=harvest_id, green_weight_kg="99.9")

    assert response.status_code == 409
    assert response.data["code"] == "harvest_id_conflict"
    assert "current" not in response.data


def test_the_id_of_another_producer_is_a_conflict_without_its_data(auth_client, field):
    harvest_id = str(uuid.uuid4())
    register(auth_client(field.foreman), field, id=harvest_id)
    other = Field(variety=CacaoVarietyFactory())

    response = register(auth_client(other.foreman), other, id=harvest_id)

    assert response.status_code == 409
    assert response.data["code"] == "harvest_id_conflict"
    assert Harvest.objects.count() == 1


def test_the_device_time_is_kept_as_information(client, field):
    register(client, field, captured_at="2026-10-14T09:12:00-05:00")

    assert Harvest.objects.get().captured_at.isoformat() == "2026-10-14T14:12:00+00:00"


def test_unknown_fields_are_rejected(client, field):
    response = register(client, field, lot="x")

    assert response.status_code == 400
    assert "lot" in response.data["fields"]


def test_yesterday_is_fine(client, field):
    assert register(client, field, harvest_date=str(TODAY - timedelta(days=1))).status_code == 201
