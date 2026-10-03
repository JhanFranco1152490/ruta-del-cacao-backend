import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.geometry import measured_area_hectares, to_polygon, validate_boundary
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.tests.factories import NEAR_SHAPES, PlotFactory, boundary_fields, rect
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

PLOT_PERMISSIONS = [
    "farms.view_farm",
    "plots.view_plot",
    "plots.add_plot",
    "plots.change_plot",
    "plots.delete_plot",
]


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory(), permissions=PLOT_PERMISSIONS)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def farm(owner):
    return FarmFactory(
        **NEAR_SHAPES, producer=owner.producer, name="La Esperanza", area_hectares=Decimal("10")
    )


def measured(vertices) -> Decimal:
    return measured_area_hectares(to_polygon(validate_boundary(vertices).vertices))


def as_json(vertices):
    return [
        {
            "latitude": str(v["latitude"]),
            "longitude": str(v["longitude"]),
            "accuracy_m": None if v["accuracy_m"] is None else str(v["accuracy_m"]),
            "captured_at": v["captured_at"],
            "source": v["source"],
        }
        for v in vertices
    ]


def body(farm, vertices=None, **overrides):
    data = {"farm_id": str(farm.pk), "code": "P1 · El Mango", "area_hectares": "1.00"}
    if vertices is not None:
        data["boundary"] = as_json(vertices)
        data["area_hectares"] = str(measured(vertices).quantize(Decimal("0.01")))
    data.update(overrides)
    return data


def drawn_plot(farm, vertices, **fields):
    area = measured(vertices).quantize(Decimal("0.01"))
    return PlotFactory(farm=farm, area_hectares=area, **boundary_fields(vertices), **fields)


# --- Acceso ------------------------------------------------------------------------------


def test_requires_a_session():
    response = APIClient().get("/api/plots")

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"


@pytest.mark.parametrize(
    "method, path_suffix, missing",
    [
        ("get", "", "plots.view_plot"),
        ("post", "", "plots.add_plot"),
        ("get", "/{id}", "plots.view_plot"),
        ("patch", "/{id}", "plots.change_plot"),
        ("delete", "/{id}?expected_version=1", "plots.delete_plot"),
    ],
)
def test_each_action_requires_its_permission(auth_client, method, path_suffix, missing):
    user = UserFactory(
        producer=ProducerFactory(),
        permissions=[code for code in PLOT_PERMISSIONS if code != missing],
    )
    plot = PlotFactory(farm=FarmFactory(**NEAR_SHAPES, producer=user.producer))

    response = getattr(auth_client(user), method)(
        "/api/plots" + path_suffix.format(id=plot.pk), {}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


# --- Registrar ---------------------------------------------------------------------------


def test_create_returns_the_plot_in_the_contract_shape(client, farm):
    # CA-1: queda asociada a la finca, con su contorno y su área calculada.
    plot_id = uuid.uuid4()
    vertices = rect(0, 0, 1, 1)
    vertices[0].update(source="gps", accuracy_m=Decimal("4.0"))
    data = body(farm, vertices, id=str(plot_id), captured_at="2026-10-01T14:10:00Z")

    response = client.post("/api/plots", data, format="json")

    assert response.status_code == 201
    assert response["Location"] == f"/api/plots/{plot_id}"
    result = response.json()
    assert result == {
        "id": str(plot_id),
        "farm": {"id": str(farm.pk), "name": "La Esperanza"},
        "code": "P1 · El Mango",
        "area_hectares": data["area_hectares"],
        "measured_area_hectares": str(measured(vertices)),
        "boundary": result["boundary"],
        "version": 1,
        "is_active": True,
        "captured_at": result["captured_at"],
        "created_at": result["created_at"],
        "updated_at": result["updated_at"],
    }
    assert result["boundary"][0] == {
        "latitude": "7.8000000",
        "longitude": "-72.5000000",
        "accuracy_m": "4.0",
        "captured_at": None,
        "source": "gps",
    }
    assert [vertex["source"] for vertex in result["boundary"]] == ["gps", "map", "map", "map"]
    assert result["captured_at"] is not None


def test_create_without_boundary(client, farm):
    # CA-12: se acepta sin contorno y se informa que no lo tiene.
    response = client.post("/api/plots", body(farm), format="json")

    assert response.status_code == 201
    assert (response.data["boundary"], response.data["measured_area_hectares"]) == (None, None)
    assert response.data["id"]


def test_resending_the_same_plot_returns_200(client, farm):
    data = body(farm, rect(0, 0, 1, 1), id=str(uuid.uuid4()))
    client.post("/api/plots", data, format="json")

    response = client.post("/api/plots", data, format="json")

    assert response.status_code == 200
    assert Plot.objects.count() == 1


def test_resending_an_id_with_other_content_returns_the_current_plot(client, farm):
    data = body(farm, id=str(uuid.uuid4()))
    client.post("/api/plots", data, format="json")

    response = client.post("/api/plots", {**data, "code": "Otro"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "plot_id_conflict"
    assert response.data["current"]["code"] == "P1 · El Mango"


def test_an_id_of_another_producer_is_a_conflict_without_its_data(client, farm):
    foreign = PlotFactory(farm=FarmFactory(**NEAR_SHAPES, producer=ProducerFactory()))

    response = client.post("/api/plots", body(farm, id=str(foreign.pk)), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "plot_id_conflict"
    assert "current" not in response.data


def test_the_plots_cannot_exceed_the_farm_area(client, farm):
    # CA-2: finca de 10 ha con 6 asignadas; 5 más no caben y la base no cambia.
    PlotFactory(farm=farm, area_hectares=Decimal("6.00"))

    response = client.post("/api/plots", body(farm, area_hectares="5.00"), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "plot_area_exceeds_farm"
    assert response.data["detail"] == "El área ingresada supera el área disponible de la finca."
    assert list(response.data["fields"]) == ["area_hectares"]
    assert farm.plots.count() == 1


def test_a_declared_area_far_from_the_drawing_returns_the_measured_area(client, farm):
    # CA-6: con el área calculada en el error, la interfaz ofrece usarla.
    vertices = rect(0, 0, 1, 1)

    response = client.post("/api/plots", body(farm, vertices, area_hectares="2.00"), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "area_mismatch"
    assert response.data["measured_area_hectares"] == str(measured(vertices))
    assert list(response.data["fields"]) == ["area_hectares"]


@pytest.mark.parametrize("shape", ["crossing", "two_vertices"])
def test_an_invalid_boundary_is_rejected(client, farm, shape):
    # CA-7: lados que se cruzan o menos de 3 vértices.
    bottom_left, bottom_right, top_right, top_left = rect(0, 0, 1, 1)
    vertices = (
        [bottom_left, top_right, bottom_right, top_left]
        if shape == "crossing"
        else [bottom_left, bottom_right]
    )
    data = body(farm, area_hectares="1.00")
    data["boundary"] = as_json(vertices)

    response = client.post("/api/plots", data, format="json")

    assert response.status_code == 422
    assert response.data["code"] == "invalid_boundary"
    assert response.data["fields"]["boundary"][0].startswith("El polígono no es válido:")


def test_an_overlap_returns_the_neighbour_and_the_suggested_boundary(client, farm):
    # CA-4 y CA-5: lo que la bandeja necesita para resaltar la zona y aplicar el ajuste.
    neighbour = drawn_plot(farm, rect(1, 0, 3, 1), code="P2")

    response = client.post("/api/plots", body(farm, rect(0, 0, 2, 1)), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "plot_overlap"
    assert response.data["fields"] == {"boundary": ["El polígono se superpone con la parcela P2."]}
    (overlap,) = response.data["overlaps"]
    assert overlap["plot_id"] == str(neighbour.pk)
    assert overlap["code"] == "P2"
    assert overlap["overlap_area_hectares"] == str(measured(rect(1, 0, 2, 1)))
    assert len(overlap["boundary"]) == 4
    suggestion = response.data["suggested_boundary"]
    assert {(Decimal(v["longitude"]), Decimal(v["latitude"])) for v in suggestion} == {
        (v["longitude"], v["latitude"]) for v in rect(0, 0, 1, 1)
    }
    assert sorted(v["source"] for v in suggestion) == ["adjusted", "adjusted", "map", "map"]
    assert response.data["suggested_measured_area_hectares"] == str(measured(rect(0, 0, 1, 1)))


def test_a_boundary_too_far_from_the_farm_point_is_a_422_that_names_the_vertex(client, farm):
    response = client.post("/api/plots", body(farm, rect(0, 20, 1, 21)[:3]), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "plot_too_far_from_farm"
    (message,) = response.data["fields"]["boundary"]
    assert message.startswith("El vértice 1 está a ")
    assert message.endswith("el máximo para esta finca es 657 m.")


def test_an_overlap_without_a_possible_suggestion(client, farm):
    farm.area_hectares = Decimal("50")
    farm.save()
    drawn_plot(farm, rect(0, 0, 3, 3), code="P2")

    response = client.post("/api/plots", body(farm, rect(1, 1, 2, 2)), format="json")

    assert response.data["code"] == "plot_overlap"
    assert response.data["suggested_boundary"] is None
    assert response.data["suggested_measured_area_hectares"] is None


def test_a_repeated_code_in_the_same_farm_is_rejected(client, farm):
    # CA-11: " p-01 " choca con "P-01" en la misma finca, no en otra.
    PlotFactory(farm=farm, code="P-01")
    other_farm = FarmFactory(**NEAR_SHAPES, producer=farm.producer)

    repeated = client.post("/api/plots", body(farm, code=" p-01 "), format="json")
    elsewhere = client.post("/api/plots", body(other_farm, code=" p-01 "), format="json")

    assert repeated.status_code == 409
    assert repeated.data["code"] == "duplicate_plot_code"
    assert elsewhere.status_code == 201


@pytest.mark.parametrize(
    "vertex_change, field",
    [
        ({"accuracy_m": "4.0"}, "accuracy_m"),
        ({"source": "satelite"}, "source"),
        ({"latitude": None}, "latitude"),
        ({"altitude": 900}, "altitude"),
    ],
    ids=["accuracy_without_gps", "unknown_source", "missing_latitude", "unknown_field"],
)
def test_each_vertex_is_validated(client, farm, vertex_change, field):
    data = body(farm, rect(0, 0, 1, 1))
    data["boundary"][1].update(vertex_change)

    response = client.post("/api/plots", data, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "boundary" in response.data["fields"]


@pytest.mark.parametrize(
    "change", [{"code": "   "}, {"area_hectares": "0"}, {"code": "x" * 51}], ids=str
)
def test_code_and_area_are_validated(client, farm, change):
    response = client.post("/api/plots", body(farm, **change), format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert set(response.data["fields"]) == set(change)


def test_a_farm_of_another_producer_does_not_exist(client):
    # CA-14 al registrar.
    foreign_farm = FarmFactory(**NEAR_SHAPES, producer=ProducerFactory())

    response = client.post("/api/plots", body(foreign_farm), format="json")

    assert response.status_code == 404
    assert not Plot.objects.exists()


def test_an_inactive_farm_rejects_new_plots(client, farm):
    farm.is_active = False
    farm.save()

    response = client.post("/api/plots", body(farm), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "farm_inactive"


# --- Consultar ---------------------------------------------------------------------------


def test_list_returns_own_plots_ordered_by_code_and_paginated(client, farm):
    for code in ["P-03", "P-01", "P-02"]:
        PlotFactory(farm=farm, code=code)
    PlotFactory(farm=FarmFactory(**NEAR_SHAPES, producer=ProducerFactory()), code="P-00")

    response = client.get("/api/plots", {"page_size": 2})

    assert response.data["count"] == 3
    assert [plot["code"] for plot in response.data["results"]] == ["P-01", "P-02"]
    assert response.data["next"] is not None


def test_list_filters_by_farm_status_and_code(client, farm):
    other_farm = FarmFactory(**NEAR_SHAPES, producer=farm.producer)
    # El prefijo fija el orden: así no depende de cómo ordene las tildes la base de datos.
    PlotFactory(farm=farm, code="A1 Árbol")
    PlotFactory(farm=farm, code="B2 Río", is_active=False)
    PlotFactory(farm=other_farm, code="C3 árbol viejo")

    def codes(**params):
        return [plot["code"] for plot in client.get("/api/plots", params).data["results"]]

    assert codes(farm=farm.pk) == ["A1 Árbol", "B2 Río"]
    assert codes(farm=farm.pk, is_active="false") == ["B2 Río"]
    assert codes(search="arbol") == ["A1 Árbol", "C3 árbol viejo"]


def test_filtering_by_a_farm_of_another_producer_returns_nothing(client):
    foreign_farm = FarmFactory(**NEAR_SHAPES, producer=ProducerFactory())
    PlotFactory(farm=foreign_farm)

    response = client.get("/api/plots", {"farm": foreign_farm.pk})

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.parametrize("params", [{"farm": "no-es-un-uuid"}, {"is_active": "quizas"}], ids=str)
def test_malformed_filters_are_rejected(client, params):
    response = client.get("/api/plots", params)

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_the_list_query_count_does_not_grow_with_plots(client, farm):
    drawn_plot(farm, rect(0, 0, 1, 1))
    with CaptureQueriesContext(connection) as one:
        client.get("/api/plots")
    for x in range(1, 6):
        drawn_plot(FarmFactory(**NEAR_SHAPES, producer=farm.producer), rect(x, 0, x + 1, 1))

    with CaptureQueriesContext(connection) as many:
        client.get("/api/plots")

    assert len(many) == len(one)


def test_retrieve_returns_an_own_plot_with_its_boundary(client, farm):
    # CA-3: con el contorno para dibujarlo junto al marcador de la finca.
    plot = drawn_plot(farm, rect(0, 0, 1, 1))

    response = client.get(f"/api/plots/{plot.pk}")

    assert response.status_code == 200
    assert len(response.data["boundary"]) == 4
    assert response.data["farm"]["id"] == str(farm.pk)


def test_a_plot_of_another_producer_does_not_exist(client):
    # CA-14 al consultar y al modificar.
    foreign = PlotFactory(
        farm=FarmFactory(**NEAR_SHAPES, producer=ProducerFactory()), code="Ajena"
    )

    got = client.get(f"/api/plots/{foreign.pk}")
    patched = client.patch(
        f"/api/plots/{foreign.pk}", {"code": "Mía", "expected_version": 1}, format="json"
    )

    assert (got.status_code, patched.status_code) == (404, 404)
    foreign.refresh_from_db()
    assert foreign.code == "Ajena"


# --- Editar ------------------------------------------------------------------------------


def test_update_edits_the_plot_and_audits_it(client, owner, farm):
    plot = PlotFactory(farm=farm)

    response = client.patch(
        f"/api/plots/{plot.pk}", {"code": "Nuevo", "expected_version": 1}, format="json"
    )

    assert response.status_code == 200
    assert (response.data["code"], response.data["version"]) == ("Nuevo", 2)
    event = PlotAuditEvent.objects.get(plot=plot)
    assert (event.action, event.actor) == ("updated", owner)


def test_update_draws_and_removes_the_boundary(client, farm):
    # CA-12, FA-2: una parcela sin contorno se dibuja después.
    plot = PlotFactory(
        farm=farm, area_hectares=measured(rect(0, 0, 1, 1)).quantize(Decimal("0.01"))
    )
    drawn = {"boundary": as_json(rect(0, 0, 1, 1)), "expected_version": 1}

    added = client.patch(f"/api/plots/{plot.pk}", drawn, format="json")
    removed = client.patch(
        f"/api/plots/{plot.pk}", {"boundary": None, "expected_version": 2}, format="json"
    )

    assert len(added.data["boundary"]) == 4
    assert (removed.data["boundary"], removed.data["measured_area_hectares"]) == (None, None)


def test_update_deactivates_and_reactivates(client, farm):
    # CA-9 por la API: desactivar libera el área y reactivar la vuelve a pedir.
    plot = PlotFactory(farm=farm, area_hectares=Decimal("6.00"))
    deactivated = client.patch(
        f"/api/plots/{plot.pk}", {"is_active": False, "expected_version": 1}, format="json"
    )
    PlotFactory(farm=farm, area_hectares=Decimal("5.00"))

    reactivated = client.patch(
        f"/api/plots/{plot.pk}", {"is_active": True, "expected_version": 2}, format="json"
    )

    assert deactivated.data["is_active"] is False
    assert reactivated.status_code == 422
    assert reactivated.data["code"] == "plot_area_exceeds_farm"


def test_update_cannot_move_a_plot_to_another_farm(client, farm):
    plot = PlotFactory(farm=farm)
    other_farm = FarmFactory(**NEAR_SHAPES, producer=farm.producer)

    response = client.patch(
        f"/api/plots/{plot.pk}",
        {"farm_id": str(other_farm.pk), "expected_version": 1},
        format="json",
    )

    assert response.status_code == 400
    assert "farm_id" in response.data["fields"]
    plot.refresh_from_db()
    assert plot.farm_id == farm.pk


@pytest.mark.parametrize("data", [{"code": "Nuevo"}, {"expected_version": 1}], ids=str)
def test_update_requires_a_version_and_a_change(client, farm, data):
    plot = PlotFactory(farm=farm)

    response = client.patch(f"/api/plots/{plot.pk}", data, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_an_outdated_version_returns_the_current_plot(client, farm):
    plot = PlotFactory(farm=farm)
    client.patch(
        f"/api/plots/{plot.pk}", {"code": "Primero", "expected_version": 1}, format="json"
    )

    response = client.patch(
        f"/api/plots/{plot.pk}", {"code": "Segundo", "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert (response.data["current"]["code"], response.data["current"]["version"]) == (
        "Primero",
        2,
    )


@pytest.mark.parametrize("method", ["post", "patch"])
def test_a_vertex_may_omit_its_optional_fields(client, farm, method):
    # En una edición parcial DRF no completa los valores por defecto, tampoco en los vértices:
    # un vértice sin `accuracy_m` ni `captured_at` debe aceptarse igual en las dos rutas.
    vertices = [
        {"latitude": v["latitude"], "longitude": v["longitude"], "source": "map"}
        for v in as_json(rect(0, 0, 1, 1))
    ]
    area = str(measured(rect(0, 0, 1, 1)).quantize(Decimal("0.01")))
    if method == "post":
        response = client.post(
            "/api/plots", body(farm, area_hectares=area, boundary=vertices), format="json"
        )
    else:
        plot = PlotFactory(farm=farm, area_hectares=Decimal(area))
        response = client.patch(
            f"/api/plots/{plot.pk}", {"boundary": vertices, "expected_version": 1}, format="json"
        )

    assert response.status_code in (200, 201)
    assert response.data["boundary"][0]["accuracy_m"] is None
    assert response.data["boundary"][0]["captured_at"] is None


# --- Eliminar ----------------------------------------------------------------------------


def test_delete_removes_a_plot_created_by_mistake(client, farm):
    plot = PlotFactory(farm=farm)

    response = client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 204
    assert not response.content
    assert client.get(f"/api/plots/{plot.pk}").status_code == 404


@pytest.mark.parametrize("query", ["", "?expected_version=cero"], ids=["missing", "not_a_number"])
def test_delete_requires_the_version_in_the_url(client, farm, query):
    plot = PlotFactory(farm=farm)

    response = client.delete(f"/api/plots/{plot.pk}{query}")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]
    assert Plot.objects.filter(pk=plot.pk).exists()


def test_delete_with_an_outdated_version_returns_the_current_plot(client, farm):
    plot = PlotFactory(farm=farm)
    client.patch(f"/api/plots/{plot.pk}", {"code": "Nuevo", "expected_version": 1}, format="json")

    response = client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2


def test_delete_in_an_inactive_farm_is_rejected(client, farm):
    plot = PlotFactory(farm=farm)
    farm.is_active = False
    farm.save()

    response = client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 422
    assert response.data["code"] == "farm_inactive"


def test_delete_with_dependent_records_suggests_deactivating(client, farm):
    plot = PlotFactory(farm=farm)

    with mock.patch("apps.plots.services.delete.has_dependent_rows", return_value=True):
        response = client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "plot_has_records"
    assert "Desactívala" in response.data["detail"]


def test_delete_of_a_plot_of_another_producer_does_not_exist(client):
    foreign = PlotFactory(farm=FarmFactory(**NEAR_SHAPES, producer=ProducerFactory()))

    response = client.delete(f"/api/plots/{foreign.pk}?expected_version=1")

    assert response.status_code == 404
    assert Plot.objects.filter(pk=foreign.pk).exists()
