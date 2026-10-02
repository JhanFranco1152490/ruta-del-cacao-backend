import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.exceptions import (
    AreaMismatch,
    DuplicatePlotCode,
    FarmInactive,
    FarmNotFound,
    InvalidBoundary,
    PlotAreaExceedsFarm,
    PlotIdConflict,
    PlotOverlap,
)
from apps.plots.geometry import measured_area_hectares, to_polygon, validate_boundary
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.services import create_plot
from apps.plots.tests.factories import (
    PlotFactory,
    boundary_fields,
    plot_data,
    rect,
)
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def farm(owner):
    return FarmFactory(producer=owner.producer, area_hectares=Decimal("10.00"))


def measured(vertices) -> Decimal:
    return measured_area_hectares(to_polygon(validate_boundary(vertices).vertices))


def with_boundary(farm, vertices, **overrides):
    """Datos de una parcela con contorno y el área declarada redondeada desde la calculada."""
    area = measured(vertices).quantize(Decimal("0.01"))
    return plot_data(farm, boundary=vertices, area_hectares=area, **overrides)


def coordinates(vertices):
    return {(Decimal(v["longitude"]), Decimal(v["latitude"])) for v in vertices}


# --- Alta válida -----------------------------------------------------------------------


def test_creates_a_plot_without_boundary_and_audits_it(owner, farm):
    plot, created = create_plot(owner, plot_data(farm, code="  P1 · El Mango "))

    assert created is True
    assert (plot.farm_id, plot.code, plot.code_normalized) == (
        farm.pk,
        "P1 · El Mango",
        "p1 · el mango",
    )
    assert (plot.version, plot.is_active) == (1, True)
    assert (plot.boundary, plot.measured_area_hectares) == (None, None)
    event = PlotAuditEvent.objects.get(plot=plot)
    assert (event.action, event.actor) == (PlotAuditEvent.Action.CREATED, owner)
    assert (event.area_hectares, event.measured_area_hectares) == (Decimal("1.00"), None)


def test_creates_a_plot_with_boundary_and_stores_its_measured_area(owner, farm):
    vertices = rect(0, 0, 1, 1)
    vertices[0].update(
        source="gps",
        accuracy_m=Decimal("4.0"),
        captured_at=datetime(2026, 10, 1, 14, 2, 10, tzinfo=UTC),
    )

    plot, _ = create_plot(owner, with_boundary(farm, vertices))

    plot.refresh_from_db()
    assert plot.measured_area_hectares == measured(vertices)
    assert plot.boundary[0] == {
        "latitude": "7.8000000",
        "longitude": "-72.5000000",
        "accuracy_m": "4.0",
        "captured_at": "2026-10-01T14:02:10+00:00",
        "source": "gps",
    }
    assert plot.boundary[2]["latitude"] == "7.8010000"
    event = PlotAuditEvent.objects.get(plot=plot)
    assert event.measured_area_hectares == plot.measured_area_hectares


def test_the_client_may_choose_the_id(owner, farm):
    plot_id = uuid.uuid4()

    plot, _ = create_plot(owner, plot_data(farm, id=plot_id))

    assert plot.pk == plot_id


def test_nothing_is_saved_if_the_audit_fails(owner, farm):
    with mock.patch.object(PlotAuditEvent, "record", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            create_plot(owner, plot_data(farm))

    assert not Plot.objects.exists()


# --- Finca -----------------------------------------------------------------------------


def test_a_farm_of_another_producer_does_not_exist(farm):
    stranger = UserFactory(producer=ProducerFactory())

    with pytest.raises(FarmNotFound):
        create_plot(stranger, plot_data(farm))


def test_an_unknown_farm_does_not_exist(owner):
    with pytest.raises(FarmNotFound):
        create_plot(owner, plot_data(FarmFactory.build()))


def test_an_inactive_farm_does_not_accept_plots(owner, farm):
    farm.is_active = False
    farm.save()

    with pytest.raises(FarmInactive):
        create_plot(owner, plot_data(farm))


# --- Validaciones del registro ---------------------------------------------------------


@pytest.mark.parametrize("code", ["", "   "])
def test_code_is_required(owner, farm, code):
    with pytest.raises(ValidationError) as error:
        create_plot(owner, plot_data(farm, code=code))

    assert "code" in error.value.message_dict


def test_area_must_be_positive(owner, farm):
    with pytest.raises(ValidationError) as error:
        create_plot(owner, plot_data(farm, area_hectares=Decimal("0")))

    assert error.value.message_dict["area_hectares"] == ["El área debe ser mayor a 0."]


def test_code_is_unique_within_the_farm(owner, farm):
    create_plot(owner, plot_data(farm, code="P-01"))

    with pytest.raises(DuplicatePlotCode):
        create_plot(owner, plot_data(farm, code=" p-01 "))


def test_the_same_code_is_accepted_in_another_farm(owner, farm):
    create_plot(owner, plot_data(farm, code="P-01"))

    create_plot(owner, plot_data(FarmFactory(producer=owner.producer), code="P-01"))


def test_an_invalid_boundary_is_rejected_and_nothing_is_saved(owner, farm):
    with pytest.raises(InvalidBoundary):
        create_plot(owner, plot_data(farm, boundary=rect(0, 0, 1, 1)[:2]))

    assert not Plot.objects.exists()


def test_a_declared_area_far_from_the_drawn_one_is_rejected_with_the_measured_area(owner, farm):
    vertices = rect(0, 0, 1, 1)

    with pytest.raises(AreaMismatch) as error:
        create_plot(owner, plot_data(farm, boundary=vertices, area_hectares=Decimal("2.00")))

    assert error.value.measured_area_hectares == measured(vertices)


def test_a_declared_area_within_five_percent_is_accepted_and_both_are_kept(owner, farm):
    vertices = rect(0, 0, 1, 1)
    declared = (measured(vertices) * Decimal("1.04")).quantize(Decimal("0.01"))

    plot, _ = create_plot(owner, plot_data(farm, boundary=vertices, area_hectares=declared))

    assert (plot.area_hectares, plot.measured_area_hectares) == (declared, measured(vertices))


# --- Área disponible -------------------------------------------------------------------


def test_the_plots_cannot_exceed_the_farm_area(owner, farm):
    PlotFactory(farm=farm, area_hectares=Decimal("6.00"))

    with pytest.raises(PlotAreaExceedsFarm):
        create_plot(owner, plot_data(farm, area_hectares=Decimal("5.00")))

    assert farm.plots.count() == 1


def test_the_remaining_area_can_be_used_exactly(owner, farm):
    PlotFactory(farm=farm, area_hectares=Decimal("6.00"))

    create_plot(owner, plot_data(farm, area_hectares=Decimal("4.00")))


def test_inactive_plots_do_not_count_for_the_farm_area(owner, farm):
    PlotFactory(farm=farm, area_hectares=Decimal("6.00"), is_active=False)

    create_plot(owner, plot_data(farm, area_hectares=Decimal("10.00")))


# --- Superposición ---------------------------------------------------------------------


def test_an_overlap_is_rejected_with_the_neighbour_and_a_suggestion(owner, farm):
    neighbour = PlotFactory(farm=farm, code="P2", **boundary_fields(rect(1, 0, 3, 1)))

    with pytest.raises(PlotOverlap) as error:
        create_plot(owner, with_boundary(farm, rect(0, 0, 2, 1)))

    ((plot, area),) = error.value.overlaps
    assert plot == neighbour
    assert area == measured(rect(1, 0, 2, 1))
    assert coordinates(error.value.suggested_boundary) == coordinates(rect(0, 0, 1, 1))
    assert error.value.suggested_measured_area_hectares == measured(rect(0, 0, 1, 1))
    assert error.value.fields == {"boundary": ["El polígono se superpone con la parcela P2."]}


def test_an_overlap_without_a_possible_suggestion_still_lists_the_neighbour(owner, farm):
    PlotFactory(farm=farm, code="P2", **boundary_fields(rect(0, 0, 3, 3)))

    with pytest.raises(PlotOverlap) as error:
        create_plot(owner, with_boundary(farm, rect(1, 1, 2, 2)))

    assert [plot.code for plot, _ in error.value.overlaps] == ["P2"]
    assert error.value.suggested_boundary is None
    assert error.value.suggested_measured_area_hectares is None


def test_sharing_a_side_with_a_neighbour_is_accepted(owner, farm):
    PlotFactory(farm=farm, **boundary_fields(rect(1, 0, 2, 1)))

    create_plot(owner, with_boundary(farm, rect(0, 0, 1, 1)))


@pytest.mark.parametrize("neighbour", ["inactive", "without_boundary", "in_another_farm"])
def test_plots_that_do_not_count_for_the_overlap(owner, farm, neighbour):
    if neighbour == "inactive":
        PlotFactory(farm=farm, is_active=False, **boundary_fields(rect(0, 0, 1, 1)))
    elif neighbour == "without_boundary":
        PlotFactory(farm=farm)
    else:
        other_farm = FarmFactory(producer=owner.producer)
        PlotFactory(farm=other_farm, **boundary_fields(rect(0, 0, 1, 1)))

    create_plot(owner, with_boundary(farm, rect(0, 0, 1, 1)))


# --- Reenvíos del mismo id -------------------------------------------------------------


def test_resending_the_same_plot_returns_it_without_duplicating(owner, farm):
    plot_id = uuid.uuid4()
    first, _ = create_plot(owner, with_boundary(farm, rect(0, 0, 1, 1), id=plot_id))
    # Las mismas coordenadas escritas de otra forma son el mismo contorno.
    rewritten = [{**v, "latitude": Decimal(f"{v['latitude']}000")} for v in rect(0, 0, 1, 1)]

    again, created = create_plot(owner, with_boundary(farm, rewritten, id=plot_id))

    assert created is False
    assert again.pk == first.pk
    assert again.version == 1
    assert Plot.objects.count() == 1
    assert PlotAuditEvent.objects.count() == 1


def test_resending_an_id_with_other_content_returns_the_current_plot(owner, farm):
    plot_id = uuid.uuid4()
    create_plot(owner, plot_data(farm, id=plot_id, code="P-01"))

    with pytest.raises(PlotIdConflict) as error:
        create_plot(owner, plot_data(farm, id=plot_id, code="P-02"))

    assert error.value.current_plot.code == "P-01"


def test_an_id_of_another_producer_is_a_conflict_without_its_data(owner, farm):
    plot = PlotFactory(farm=farm)
    stranger = UserFactory(producer=ProducerFactory())
    their_farm = FarmFactory(producer=stranger.producer)

    with pytest.raises(PlotIdConflict) as error:
        create_plot(stranger, plot_data(their_farm, id=plot.pk))

    assert error.value.current_plot is None


def test_resending_does_not_need_the_farm_to_be_active(owner, farm):
    plot_id = uuid.uuid4()
    create_plot(owner, plot_data(farm, id=plot_id))
    farm.is_active = False
    farm.save()

    _, created = create_plot(owner, plot_data(farm, id=plot_id))

    assert created is False
