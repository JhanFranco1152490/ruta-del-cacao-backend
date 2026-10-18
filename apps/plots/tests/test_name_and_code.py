"""El código de la parcela lo asigna el servidor (`P05`) y su nombre es opcional y editable."""

from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot
from apps.plots.tests.factories import NEAR_SHAPES, PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

PERMISSIONS = ["farms.view_farm", "plots.view_plot", "plots.add_plot", "plots.change_plot"]


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory(), permissions=PERMISSIONS)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def farm(owner):
    return FarmFactory(
        **NEAR_SHAPES, producer=owner.producer, name="La Esperanza", area_hectares=Decimal("50")
    )


def create(client, farm, **fields):
    return client.post(
        "/api/plots",
        {"farm_id": str(farm.pk), "area_hectares": "1.00", **fields},
        format="json",
    )


def patch(client, plot, **fields):
    return client.patch(
        f"/api/plots/{plot.pk}", {"expected_version": plot.version, **fields}, format="json"
    )


def test_a_new_plot_gets_its_code_from_the_server_and_may_have_no_name(client, farm):
    response = create(client, farm)

    assert response.status_code == 201
    assert response.data["code"] == "P01"
    assert response.data["name"] is None
    assert response.data["farm"]["code"] == "F01"


def test_a_plot_can_be_named(client, farm):
    response = create(client, farm, name="  Lote del río ")

    assert response.data["name"] == "Lote del río"
    assert response.data["code"] == "P01"


def test_plots_without_a_name_can_coexist_in_the_same_farm(client, farm):
    assert create(client, farm).status_code == 201
    assert create(client, farm).status_code == 201

    assert Plot.objects.filter(farm=farm, name__isnull=True).count() == 2


def test_a_blank_name_is_the_same_as_no_name(client, farm):
    response = create(client, farm, name="   ")

    assert response.status_code == 201
    assert response.data["name"] is None
    assert create(client, farm, name="").status_code == 201


def test_a_repeated_name_is_a_conflict_ignoring_case_and_surrounding_spaces(client, farm):
    create(client, farm, name="Lote del río")

    response = create(client, farm, name="  LOTE del RÍO ")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_plot_name"
    assert "name" in response.data["fields"]


def test_the_same_name_in_another_farm_is_fine(client, owner, farm):
    other = FarmFactory(**NEAR_SHAPES, producer=owner.producer, area_hectares=Decimal("50"))
    create(client, farm, name="La loma")

    assert create(client, other, name="La loma").status_code == 201


def test_a_name_longer_than_sixty_characters_is_rejected(client, farm):
    response = create(client, farm, name="x" * 61)

    assert response.status_code == 400
    assert "name" in response.data["fields"]


def test_a_queued_plot_from_an_older_app_keeps_its_code_as_the_name(client, farm):
    response = create(client, farm, code="Lote del río")

    assert response.status_code == 201
    assert response.data["name"] == "Lote del río"
    assert response.data["code"] == "P01"


def test_when_both_arrive_the_old_code_is_ignored(client, farm):
    response = create(client, farm, code="P-03", name="La loma")

    assert response.data["name"] == "La loma"
    assert response.data["code"] == "P01"


def test_an_old_code_that_repeats_a_name_is_a_duplicate(client, farm):
    create(client, farm, name="Lote del río")

    response = create(client, farm, code="lote del río")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_plot_name"


def test_the_code_cannot_be_edited(client, owner, farm):
    plot = PlotFactory(farm=farm)

    response = patch(client, plot, code="P99")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "code" in response.data["fields"]
    plot.refresh_from_db()
    assert plot.code == "P01"


def test_the_name_can_be_changed_and_removed(client, farm):
    plot = PlotFactory(farm=farm, name="Vieja")

    renamed = patch(client, plot, name="Nueva")
    plot.refresh_from_db()
    removed = patch(client, plot, name=None)

    assert renamed.data["name"] == "Nueva"
    assert removed.status_code == 200
    assert removed.data["name"] is None
    assert removed.data["code"] == "P01"


def test_renaming_to_a_name_in_use_is_a_conflict(client, farm):
    PlotFactory(farm=farm, name="La loma")
    other = PlotFactory(farm=farm, name="El río")

    response = patch(client, other, name="la LOMA")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_plot_name"


def test_search_finds_a_plot_by_its_code(client, farm):
    PlotFactory(farm=farm, name="Alfa")
    PlotFactory(farm=farm, name="Beta")
    PlotFactory(farm=farm, name="Gamma")

    for term in ("P02", "p2", "P 02"):
        response = client.get("/api/plots", {"search": term})
        assert [plot["name"] for plot in response.data["results"]] == ["Beta"]


def test_search_finds_a_plot_by_its_name_without_accents(client, farm):
    PlotFactory(farm=farm, name="Lote del río")
    PlotFactory(farm=farm, name="La loma")

    response = client.get("/api/plots", {"search": "RIO"})

    assert [plot["name"] for plot in response.data["results"]] == ["Lote del río"]


def test_plots_are_listed_in_the_order_of_their_code_not_their_name(client, farm):
    PlotFactory(farm=farm, name="Zeta")
    PlotFactory(farm=farm, name="Alfa")
    PlotFactory(farm=farm, name=None)

    response = client.get("/api/plots")

    assert [plot["code"] for plot in response.data["results"]] == ["P01", "P02", "P03"]


def test_the_hundredth_plot_has_a_three_digit_code(client, farm):
    farm.plot_sequence = 99
    farm.save()

    assert create(client, farm).data["code"] == "P100"
