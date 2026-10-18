"""Un empleado solo alcanza lo de la finca en la que trabaja, en cada recurso que cuelga de una.

Cada caso es un recurso: su listado, su detalle y, si aplica, una escritura. Las mismas llamadas
se hacen con un empleado de la finca A, uno sin finca y el Productor, contra datos de A y de B. Un
recurso nuevo que cuelgue de una finca agrega aquí su caso.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest

from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.activities.choices import ActivityType
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.health.tests.factories import (
    DetectionFactory,
    PhytosanitaryMonitoringFactory,
    done_monitoring,
)
from apps.lots.tests.factories import LotFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

FIELD_PERMISSIONS = [
    "farms.view_farm",
    "farms.change_farm",
    "plots.view_plot",
    "plots.add_plot",
    "plots.change_plot",
    "crops.change_plotcharacterization",
    "inputs.view_agriculturalinput",
    "activities.view_agriculturalactivity",
    "activities.add_agriculturalactivity",
    "activities.change_agriculturalactivity",
    "activities.complete_agriculturalactivity",
    "facilities.view_postharvestfacility",
    "facilities.add_postharvestfacility",
    "facilities.change_postharvestfacility",
]


class World:
    """Un productor con dos fincas, cada una con su parcela y su actividad programada."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm_a = FarmFactory(producer=self.producer, name="A")
        self.farm_b = FarmFactory(producer=self.producer, name="B")
        self.plot_a = PlotFactory(farm=self.farm_a, name="A-1")
        self.plot_b = PlotFactory(farm=self.farm_b, name="B-1")
        soon = today_in_bogota() + timedelta(days=3)
        self.owner = make_producer_owner(self.producer)
        self.activity_a = AgriculturalActivityFactory(
            plot=self.plot_a, scheduled_date=soon, assignee=self.owner
        )
        self.activity_b = AgriculturalActivityFactory(
            plot=self.plot_b, scheduled_date=soon, assignee=self.owner
        )
        self.facility_a = PostharvestFacilityFactory(farm=self.farm_a)
        self.facility_b = PostharvestFacilityFactory(farm=self.farm_b)
        self.employee = make_delegate(self.producer, FIELD_PERMISSIONS, farm=self.farm_a)
        self.unassigned = make_delegate(self.producer, FIELD_PERMISSIONS)
        self.window = {
            "from": str(today_in_bogota()),
            "to": str(today_in_bogota() + timedelta(days=30)),
        }


@pytest.fixture
def world():
    return World()


def ids(response) -> set[str]:
    assert response.status_code == 200, response.data
    return {str(row["id"]) for row in response.data["results"]}


# Cada recurso: cómo se lista, y qué registro es de la finca A y cuál de la B.
LISTS = {
    "farms": (lambda w: ("/api/farms", {}), "farm_a", "farm_b"),
    "plots": (lambda w: ("/api/plots", {}), "plot_a", "plot_b"),
    "activities": (
        lambda w: ("/api/agricultural-activities", w.window),
        "activity_a",
        "activity_b",
    ),
    "pending_activities": (
        lambda w: (
            "/api/agricultural-activities/pending",
            {"through": w.window["to"]},
        ),
        "activity_a",
        "activity_b",
    ),
    "facilities": (lambda w: ("/api/postharvest-facilities", {}), "facility_a", "facility_b"),
}

DETAILS = {
    "farm": ("/api/farms/{}", "farm_a", "farm_b"),
    "plot": ("/api/plots/{}", "plot_a", "plot_b"),
    "activity": ("/api/agricultural-activities/{}", "activity_a", "activity_b"),
    "facility": ("/api/postharvest-facilities/{}", "facility_a", "facility_b"),
}


@pytest.mark.parametrize("resource", LISTS)
def test_an_employee_lists_only_what_is_in_its_farm(auth_client, world, resource):
    request, own, foreign = LISTS[resource]
    url, params = request(world)

    listed = ids(auth_client(world.employee).get(url, params))

    assert listed == {str(getattr(world, own).pk)}
    assert str(getattr(world, foreign).pk) not in listed


@pytest.mark.parametrize("resource", LISTS)
def test_an_employee_without_a_farm_lists_nothing(auth_client, world, resource):
    url, params = LISTS[resource][0](world)

    assert ids(auth_client(world.unassigned).get(url, params)) == set()


@pytest.mark.parametrize("resource", LISTS)
def test_the_producer_lists_every_farm(auth_client, world, resource):
    request, own, foreign = LISTS[resource]
    url, params = request(world)

    listed = ids(auth_client(world.owner).get(url, params))

    assert listed == {str(getattr(world, own).pk), str(getattr(world, foreign).pk)}


@pytest.mark.parametrize("resource", DETAILS)
def test_what_is_in_another_farm_does_not_exist_for_an_employee(auth_client, world, resource):
    url, own, foreign = DETAILS[resource]
    client = auth_client(world.employee)

    assert client.get(url.format(getattr(world, own).pk)).status_code == 200
    # El mismo 404 de algo que no existe: no confirma que el productor tiene otra finca.
    response = client.get(url.format(getattr(world, foreign).pk))
    assert (response.status_code, response.data["code"]) == (404, "not_found")


@pytest.mark.parametrize("resource", DETAILS)
def test_an_employee_without_a_farm_reaches_no_record(auth_client, world, resource):
    url, own, _ = DETAILS[resource]

    assert auth_client(world.unassigned).get(url.format(getattr(world, own).pk)).status_code == 404


def test_the_farm_filter_of_another_farm_gives_nothing(auth_client, world):
    response = auth_client(world.employee).get("/api/plots", {"farm": str(world.farm_b.pk)})

    assert ids(response) == set()


# --- Escrituras ---


def test_an_employee_edits_its_farm_but_not_another(auth_client, world):
    client = auth_client(world.employee)
    body = {"details": "Portón verde", "expected_version": 1}

    assert client.patch(f"/api/farms/{world.farm_a.pk}", body, format="json").status_code == 200
    assert client.patch(f"/api/farms/{world.farm_b.pk}", body, format="json").status_code == 404


def test_an_employee_registers_plots_only_in_its_farm(auth_client, world):
    client = auth_client(world.employee)

    def register(farm):
        return client.post(
            "/api/plots",
            {"farm_id": str(farm.pk), "name": "Nueva", "area_hectares": "1.00"},
            format="json",
        )

    assert register(world.farm_a).status_code == 201
    assert register(world.farm_b).status_code == 404


def test_an_employee_edits_plots_only_in_its_farm(auth_client, world):
    client = auth_client(world.employee)
    body = {"name": "Renombrada", "expected_version": 1}

    assert client.patch(f"/api/plots/{world.plot_a.pk}", body, format="json").status_code == 200
    assert client.patch(f"/api/plots/{world.plot_b.pk}", body, format="json").status_code == 404


def characterization(variety) -> dict:
    return {
        "expected_version": None,
        "plantings": [
            {
                "variety_id": str(variety.pk),
                "planting_date": "2021-03",
                "tree_count": 100,
                "propagation": "grafted",
                "stage": "full_production",
            }
        ],
        "management_system": "conventional",
        "shade_type": None,
    }


def test_an_employee_characterizes_plots_only_in_its_farm(auth_client, world):
    client = auth_client(world.employee)
    body = characterization(CacaoVarietyFactory())

    own = client.put(f"/api/plot-characterizations/{world.plot_a.pk}", body, format="json")
    foreign = client.put(f"/api/plot-characterizations/{world.plot_b.pk}", body, format="json")

    assert own.status_code == 201, own.data
    assert foreign.status_code == 404
    assert client.get(f"/api/plot-characterizations/{world.plot_b.pk}").status_code == 404
    assert client.get(f"/api/plot-characterizations/{world.plot_b.pk}/history").status_code == 404


def schedule(client, plot, assignee):
    return client.post(
        "/api/agricultural-activities",
        {
            "plot_id": str(plot.pk),
            "activity_type": "pruning",
            "scheduled_date": str(today_in_bogota() + timedelta(days=5)),
            "assignee_id": str(assignee.pk),
        },
        format="json",
    )


def test_an_employee_schedules_only_in_its_farm(auth_client, world):
    client = auth_client(world.employee)

    assert schedule(client, world.plot_a, world.employee).status_code == 201
    # Como si la parcela no existiera, aunque sea de su mismo productor.
    assert schedule(client, world.plot_b, world.employee).status_code == 404


def test_an_employee_changes_and_completes_only_what_is_in_its_farm(auth_client, world):
    client = auth_client(world.employee)
    reschedule = {
        "scheduled_date": str(today_in_bogota() + timedelta(days=9)),
        "expected_version": 1,
    }
    done = {"done_date": str(today_in_bogota())}
    foreign = f"/api/agricultural-activities/{world.activity_b.pk}"
    own = f"/api/agricultural-activities/{world.activity_a.pk}"

    assert client.patch(foreign, reschedule, format="json").status_code == 404
    assert client.post(f"{foreign}/completion", done, format="json").status_code == 404
    assert client.patch(own, reschedule, format="json").status_code == 200


def test_an_employee_does_not_assign_work_to_the_producer(auth_client, world):
    response = schedule(auth_client(world.employee), world.plot_a, world.owner)

    assert (response.status_code, response.data["code"]) == (422, "assignee_not_available")
    assert "assignee_id" in response.data["fields"]


def test_an_employee_reassigns_within_its_farm_only(auth_client, world):
    colleague = make_delegate(world.producer, FIELD_PERMISSIONS, farm=world.farm_a)
    elsewhere = make_delegate(world.producer, FIELD_PERMISSIONS, farm=world.farm_b)
    client = auth_client(world.employee)
    url = f"/api/agricultural-activities/{world.activity_a.pk}"

    outside = client.patch(
        url, {"assignee_id": str(elsewhere.pk), "expected_version": 1}, format="json"
    )
    inside = client.patch(
        url, {"assignee_id": str(colleague.pk), "expected_version": 1}, format="json"
    )

    assert (outside.status_code, outside.data["code"]) == (422, "assignee_not_available")
    assert inside.status_code == 200
    # Ya no es del Productor: el empleado no se la puede devolver.
    back = client.patch(
        url, {"assignee_id": str(world.owner.pk), "expected_version": 2}, format="json"
    )
    assert back.status_code == 422


def test_the_producer_writes_in_any_of_its_farms(auth_client, world):
    client = auth_client(world.owner)

    assert schedule(client, world.plot_a, world.owner).status_code == 201
    assert schedule(client, world.plot_b, world.owner).status_code == 201


# --- Cosechas y lotes ---

HARVEST_FIELD_PERMISSIONS = [
    "farms.view_farm",
    "plots.view_plot",
    "harvests.view_harvest",
    "harvests.add_harvest",
    "harvests.change_harvest",
    "lots.view_lot",
    "lots.add_lot",
]


class HarvestWorld:
    """Un productor con dos fincas, cada una con una parcela con ficha, su cosecha y su lote."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm_a = FarmFactory(producer=self.producer, name="A")
        self.farm_b = FarmFactory(producer=self.producer, name="B")
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.harvest_a = HarvestFactory(plot=self.plot_a)
        self.harvest_b = HarvestFactory(plot=self.plot_b)
        self.lot_a = LotFactory(harvest=self.harvest_a)
        self.lot_b = LotFactory(harvest=self.harvest_b)
        self.free_a = HarvestFactory(plot=self.plot_a, harvest_date=self.harvest_a.harvest_date)
        self.free_b = HarvestFactory(plot=self.plot_b, harvest_date=self.harvest_b.harvest_date)
        self.owner = make_producer_owner(self.producer)
        self.employee = make_delegate(self.producer, HARVEST_FIELD_PERMISSIONS, farm=self.farm_a)
        self.unassigned = make_delegate(self.producer, HARVEST_FIELD_PERMISSIONS)
        self.window = {"from": "2026-10-01", "to": "2026-10-31"}


@pytest.fixture
def harvest_world():
    return HarvestWorld()


HARVEST_LISTS = {
    "harvests": (
        lambda w: ("/api/harvests", w.window),
        {"harvest_a", "free_a"},
        {"harvest_b", "free_b"},
    ),
    "lots": (lambda w: ("/api/lots", {}), {"lot_a"}, {"lot_b"}),
}

HARVEST_DETAILS = {
    "harvest": ("/api/harvests/{}", "harvest_a", "harvest_b"),
    "lot": ("/api/lots/{}", "lot_a", "lot_b"),
}


def names(world, attributes) -> set[str]:
    return {str(getattr(world, name).pk) for name in attributes}


@pytest.mark.parametrize("resource", HARVEST_LISTS)
def test_an_employee_lists_only_the_harvest_records_of_its_farm(
    auth_client, harvest_world, resource
):
    request, own, foreign = HARVEST_LISTS[resource]
    url, params = request(harvest_world)

    listed = ids(auth_client(harvest_world.employee).get(url, params))

    assert listed == names(harvest_world, own)
    assert not listed & names(harvest_world, foreign)


@pytest.mark.parametrize("resource", HARVEST_LISTS)
def test_an_employee_without_a_farm_lists_no_harvest_record(auth_client, harvest_world, resource):
    url, params = HARVEST_LISTS[resource][0](harvest_world)

    assert ids(auth_client(harvest_world.unassigned).get(url, params)) == set()


@pytest.mark.parametrize("resource", HARVEST_LISTS)
def test_the_producer_lists_the_harvest_records_of_every_farm(
    auth_client, harvest_world, resource
):
    request, own, foreign = HARVEST_LISTS[resource]
    url, params = request(harvest_world)

    listed = ids(auth_client(harvest_world.owner).get(url, params))

    assert listed == names(harvest_world, own) | names(harvest_world, foreign)


@pytest.mark.parametrize("resource", HARVEST_DETAILS)
def test_a_harvest_record_in_another_farm_does_not_exist_for_an_employee(
    auth_client, harvest_world, resource
):
    url, own, foreign = HARVEST_DETAILS[resource]
    client = auth_client(harvest_world.employee)

    assert client.get(url.format(getattr(harvest_world, own).pk)).status_code == 200
    response = client.get(url.format(getattr(harvest_world, foreign).pk))
    assert (response.status_code, response.data["code"]) == (404, "not_found")


@pytest.mark.parametrize("resource", HARVEST_DETAILS)
def test_an_employee_without_a_farm_reaches_no_harvest_record(
    auth_client, harvest_world, resource
):
    url, own, _ = HARVEST_DETAILS[resource]

    response = auth_client(harvest_world.unassigned).get(
        url.format(getattr(harvest_world, own).pk)
    )

    assert response.status_code == 404


def test_the_harvest_filters_of_another_farm_give_nothing(auth_client, harvest_world):
    client = auth_client(harvest_world.employee)
    other = {"farm": str(harvest_world.farm_b.pk)}

    assert ids(client.get("/api/harvests", {**harvest_world.window, **other})) == set()
    assert ids(client.get("/api/lots", other)) == set()


def test_an_employee_registers_corrects_and_conforms_only_in_its_farm(auth_client, harvest_world):
    world = harvest_world
    client = auth_client(world.employee)

    def register(plot, collector):
        variety = plot.characterization.plantings.first().variety
        return client.post(
            "/api/harvests",
            {
                "plot_id": str(plot.pk),
                "harvest_date": "2026-10-14",
                "green_weight_kg": "50.0",
                "variety_id": str(variety.pk),
                "collector_id": str(collector.pk),
            },
            format="json",
        )

    patch = {"expected_version": 1, "green_weight_kg": "60.0"}

    assert register(world.plot_a, world.employee).status_code == 201
    assert register(world.plot_b, world.employee).status_code == 404
    assert (
        client.patch(f"/api/harvests/{world.free_a.pk}", patch, format="json").status_code == 200
    )
    assert (
        client.patch(f"/api/harvests/{world.free_b.pk}", patch, format="json").status_code == 404
    )
    assert (
        client.post("/api/lots", {"harvest_id": str(world.free_a.pk)}, format="json").status_code
        == 201
    )
    assert (
        client.post("/api/lots", {"harvest_id": str(world.free_b.pk)}, format="json").status_code
        == 404
    )


def test_an_employee_deletes_nothing_without_the_permission(auth_client, harvest_world):
    client = auth_client(harvest_world.employee)

    assert (
        client.delete(f"/api/harvests/{harvest_world.free_a.pk}?expected_version=1").status_code
        == 403
    )
    assert (
        client.delete(f"/api/lots/{harvest_world.lot_a.pk}?expected_version=1").status_code == 403
    )


def test_the_collectors_offered_are_the_ones_of_the_farm_of_the_employee(
    auth_client, harvest_world
):
    world = harvest_world
    colleague = make_delegate(world.producer, ["harvests.add_harvest"], farm=world.farm_a)
    elsewhere = make_delegate(world.producer, ["harvests.add_harvest"], farm=world.farm_b)

    response = auth_client(world.employee).get("/api/harvests/collectors")

    listed = {str(row["id"]): row for row in response.data["results"]}
    assert str(colleague.pk) in listed and listed[str(colleague.pk)]["assignable"] is True
    assert str(elsewhere.pk) not in listed
    # El Productor figura, pero un empleado no le asigna una recolección.
    assert listed[str(world.owner.pk)]["assignable"] is False


def test_the_producer_writes_in_any_of_its_farms_for_harvests(auth_client, harvest_world):
    client = auth_client(harvest_world.owner)

    for harvest in (harvest_world.free_a, harvest_world.free_b):
        response = client.patch(
            f"/api/harvests/{harvest.pk}",
            {"expected_version": 1, "green_weight_kg": "10.0"},
            format="json",
        )
        assert response.status_code == 200


# --- Sanidad ---


def recorded_monitoring(plot, assignee):
    """Un monitoreo de `plot` ya registrado, con una detección que espera un control."""
    monitoring = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, assignee=assignee)
    )
    return DetectionFactory(monitoring=monitoring, requested=True)


def test_an_employee_sees_the_health_of_its_farm_only(auth_client, world):
    own = recorded_monitoring(world.plot_a, world.owner)
    foreign = recorded_monitoring(world.plot_b, world.owner)
    client = auth_client(world.employee)

    waiting = ids(client.get("/api/phytosanitary-detections/without-control"))
    history = "/api/phytosanitary-history"

    assert waiting == {str(own.pk)}
    assert str(foreign.pk) not in waiting
    assert client.get(history, {"plot": str(world.plot_a.pk)}).status_code == 200
    assert client.get(history, {"plot": str(world.plot_b.pk)}).status_code == 404
    # Sin acotar, solo trae lo de su finca.
    assert ids(client.get(history)) == {str(own.monitoring.activity_id)}


def test_an_employee_without_a_farm_sees_no_health_record(auth_client, world):
    recorded_monitoring(world.plot_a, world.owner)
    client = auth_client(world.unassigned)

    assert ids(client.get("/api/phytosanitary-detections/without-control")) == set()
    plot = {"plot": str(world.plot_a.pk)}
    assert client.get("/api/phytosanitary-history", plot).status_code == 404


def test_the_producer_sees_the_health_of_every_farm(auth_client, world):
    own = recorded_monitoring(world.plot_a, world.owner)
    foreign = recorded_monitoring(world.plot_b, world.owner)

    waiting = ids(auth_client(world.owner).get("/api/phytosanitary-detections/without-control"))

    assert waiting == {str(own.pk), str(foreign.pk)}


def test_an_employee_records_monitorings_and_controls_only_in_its_farm(auth_client, world):
    def monitoring_in(plot):
        return AgriculturalActivityFactory(
            plot=plot,
            activity_type=ActivityType.PHYTOSANITARY_MONITORING,
            scheduled_date=today_in_bogota(),
            assignee=world.employee,
        )

    def result():
        return {
            "done_date": str(today_in_bogota()),
            "sampling_unit": "trees",
            "evaluated_units": 50,
            "no_presence": True,
        }

    def control():
        return {
            "id": str(uuid.uuid4()),
            "mode": "scheduled",
            "scheduled_date": str(today_in_bogota() + timedelta(days=2)),
            "assignee_id": str(world.employee.pk),
        }

    client = auth_client(world.employee)
    record = "/api/agricultural-activities/{}/monitoring"
    controls = "/api/phytosanitary-detections/{}/controls"
    detection_a = recorded_monitoring(world.plot_a, world.owner)
    detection_b = recorded_monitoring(world.plot_b, world.owner)

    own = client.post(record.format(monitoring_in(world.plot_a).pk), result(), format="json")
    foreign = client.post(record.format(monitoring_in(world.plot_b).pk), result(), format="json")

    assert (own.status_code, foreign.status_code) == (201, 404)
    assert (
        client.post(controls.format(detection_a.pk), control(), format="json").status_code == 201
    )
    assert (
        client.post(controls.format(detection_b.pk), control(), format="json").status_code == 404
    )
