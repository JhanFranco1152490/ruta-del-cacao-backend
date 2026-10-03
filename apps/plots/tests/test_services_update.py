import uuid
from decimal import Decimal
from unittest import mock

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.exceptions import (
    AreaMismatch,
    DuplicatePlotCode,
    FarmInactive,
    PlotAreaExceedsFarm,
    PlotNotFound,
    PlotOverlap,
    PlotTooFarFromFarm,
    StalePlotVersion,
)
from apps.plots.geometry import measured_area_hectares, to_polygon, validate_boundary
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.services import create_plot, rules, update_plot
from apps.plots.tests.factories import NEAR_SHAPES, PlotFactory, boundary_fields, plot_data, rect
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def farm(owner):
    return FarmFactory(**NEAR_SHAPES, producer=owner.producer, area_hectares=Decimal("10.00"))


def measured(vertices) -> Decimal:
    return measured_area_hectares(to_polygon(validate_boundary(vertices).vertices))


def drawn(vertices) -> dict:
    """Un contorno y el área declarada que le corresponde."""
    return {"boundary": vertices, "area_hectares": measured(vertices).quantize(Decimal("0.01"))}


def drawn_plot(farm, vertices, **fields):
    area = measured(vertices).quantize(Decimal("0.01"))
    return PlotFactory(farm=farm, area_hectares=area, **boundary_fields(vertices), **fields)


def audit_actions(plot):
    return list(
        PlotAuditEvent.objects.filter(plot=plot)
        .order_by("occurred_at")
        .values_list("action", "changed_fields")
    )


# --- Editar ------------------------------------------------------------------------------


def test_edits_the_plot_raises_its_version_and_audits_the_changed_fields(owner, farm):
    plot = PlotFactory(farm=farm, code="P-01")

    updated = update_plot(owner, plot.pk, 1, {"code": " P-01 Norte ", "area_hectares": "2.5"})

    assert (updated.code, updated.code_normalized) == ("P-01 Norte", "p-01 norte")
    assert (updated.area_hectares, updated.version) == (Decimal("2.50"), 2)
    assert audit_actions(plot) == [("updated", ["area_hectares", "code"])]
    assert PlotAuditEvent.objects.get(plot=plot).area_hectares == Decimal("2.50")


def test_nothing_changes_when_the_values_are_the_same(owner, farm):
    plot = PlotFactory(farm=farm, code="P-01", area_hectares=Decimal("1.00"))

    updated = update_plot(owner, plot.pk, 1, {"code": "P-01 ", "area_hectares": "1.0"})

    assert updated.version == 1
    assert audit_actions(plot) == []


def test_a_plot_of_another_producer_does_not_exist(farm):
    plot = PlotFactory(farm=farm)
    stranger = UserFactory(producer=ProducerFactory())

    with pytest.raises(PlotNotFound):
        update_plot(stranger, plot.pk, 1, {"code": "Mía"})


def test_an_unknown_plot_does_not_exist(owner):
    with pytest.raises(PlotNotFound):
        update_plot(owner, uuid.uuid4(), 1, {"code": "P-01"})


def test_a_repeated_code_in_the_same_farm_is_rejected(owner, farm):
    PlotFactory(farm=farm, code="P-01")
    plot = PlotFactory(farm=farm, code="P-02")

    with pytest.raises(DuplicatePlotCode):
        update_plot(owner, plot.pk, 1, {"code": "p-01"})


def test_an_inactive_farm_rejects_every_change(owner, farm):
    plot = PlotFactory(farm=farm)
    farm.is_active = False
    farm.save()

    for change in ({"code": "Otro"}, {"is_active": False}):
        with pytest.raises(FarmInactive):
            update_plot(owner, plot.pk, 1, change)


# --- Versión -----------------------------------------------------------------------------


def test_an_outdated_version_is_rejected_with_the_current_plot(owner, farm):
    plot = PlotFactory(farm=farm, code="P-01")
    update_plot(owner, plot.pk, 1, {"code": "Del primer teléfono"})

    with pytest.raises(StalePlotVersion) as error:
        update_plot(owner, plot.pk, 1, {"code": "Del segundo teléfono"})

    assert (error.value.current_plot.code, error.value.current_plot.version) == (
        "Del primer teléfono",
        2,
    )


def test_retrying_an_edit_whose_response_was_lost_succeeds_without_another_version(owner, farm):
    plot = PlotFactory(farm=farm)
    update_plot(owner, plot.pk, 1, {"area_hectares": Decimal("2.00")})

    retried = update_plot(owner, plot.pk, 1, {"area_hectares": Decimal("2.0")})

    assert retried.version == 2
    assert len(audit_actions(plot)) == 1


# --- Área --------------------------------------------------------------------------------


def test_editing_a_plot_does_not_count_its_previous_area(owner, farm):
    # Finca de 10 ha con 6 asignadas, 3 de ellas de la parcela que se edita: puede llegar a 7.
    plot = PlotFactory(farm=farm, area_hectares=Decimal("3.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("3.00"))

    update_plot(owner, plot.pk, 1, {"area_hectares": Decimal("7.00")})

    with pytest.raises(PlotAreaExceedsFarm):
        update_plot(owner, plot.pk, 2, {"area_hectares": Decimal("7.01")})


def test_changing_only_the_declared_area_still_has_to_match_the_drawing(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 1, 1))

    with pytest.raises(AreaMismatch) as error:
        update_plot(owner, plot.pk, 1, {"area_hectares": Decimal("2.00")})

    assert error.value.measured_area_hectares == plot.measured_area_hectares


def test_an_inactive_plot_can_be_edited_beyond_the_available_area(owner, farm):
    # Mientras está inactiva no ocupa área: se valida al reactivarla.
    plot = PlotFactory(farm=farm, is_active=False)
    PlotFactory(farm=farm, area_hectares=Decimal("9.00"))

    update_plot(owner, plot.pk, 1, {"area_hectares": Decimal("5.00")})


# --- Contorno ----------------------------------------------------------------------------


def test_drawing_the_boundary_of_a_plot_without_one(owner, farm):
    plot = PlotFactory(farm=farm)

    updated = update_plot(owner, plot.pk, 1, drawn(rect(0, 0, 1, 1)))

    assert updated.measured_area_hectares == measured(rect(0, 0, 1, 1))
    assert len(updated.boundary) == 4
    assert audit_actions(plot) == [("updated", ["area_hectares", "boundary"])]


def test_the_boundary_is_replaced_whole(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 1, 1))

    updated = update_plot(owner, plot.pk, 1, drawn(rect(0, 0, 1, 2)[:3]))

    assert len(updated.boundary) == 3
    assert updated.measured_area_hectares == measured(rect(0, 0, 1, 2)[:3])


def test_sending_null_removes_the_boundary_and_its_measured_area(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 1, 1))

    updated = update_plot(owner, plot.pk, 1, {"boundary": None})

    updated.refresh_from_db()
    assert (updated.boundary, updated.measured_area_hectares) == (None, None)
    assert audit_actions(plot) == [("updated", ["boundary"])]


def test_the_previous_boundary_of_the_plot_is_not_a_neighbour(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 2, 2))

    update_plot(owner, plot.pk, 1, drawn(rect(1, 1, 3, 3)))


def test_a_new_boundary_cannot_invade_a_neighbour(owner, farm):
    drawn_plot(farm, rect(1, 0, 2, 1), code="P2")
    plot = drawn_plot(farm, rect(0, 0, 1, 1))

    with pytest.raises(PlotOverlap) as error:
        update_plot(owner, plot.pk, 1, drawn(rect(0, 0, 2, 1)))

    assert [neighbour.code for neighbour, _ in error.value.overlaps] == ["P2"]


# --- Activar y desactivar ----------------------------------------------------------------


def test_deactivating_frees_the_area_and_records_a_status_change(owner, farm):
    plot = PlotFactory(farm=farm, area_hectares=Decimal("6.00"))

    update_plot(owner, plot.pk, 1, {"is_active": False})

    assert audit_actions(plot) == [("status_changed", ["is_active"])]
    create_plot(owner, plot_data(farm, area_hectares=Decimal("10.00")))


def test_a_deactivated_boundary_no_longer_blocks_its_neighbours(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 1, 1))
    update_plot(owner, plot.pk, 1, {"is_active": False})

    create_plot(owner, plot_data(farm, code="Nueva", **drawn(rect(0, 0, 1, 1))))


def test_reactivating_checks_the_available_area_again(owner, farm):
    plot = PlotFactory(farm=farm, area_hectares=Decimal("6.00"), is_active=False)
    PlotFactory(farm=farm, area_hectares=Decimal("5.00"))

    with pytest.raises(PlotAreaExceedsFarm):
        update_plot(owner, plot.pk, 1, {"is_active": True})


def test_reactivating_checks_the_overlap_again(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 1, 1), is_active=False)
    drawn_plot(farm, rect(0, 0, 1, 1), code="Ocupante")

    with pytest.raises(PlotOverlap):
        update_plot(owner, plot.pk, 1, {"is_active": True})


def test_editing_and_deactivating_at_once_records_both_events(owner, farm):
    plot = PlotFactory(farm=farm)

    update_plot(owner, plot.pk, 1, {"code": "Retirada", "is_active": False})

    assert sorted(audit_actions(plot)) == [
        ("status_changed", ["is_active"]),
        ("updated", ["code"]),
    ]


def test_a_plot_deleted_while_waiting_for_the_farm_lock_is_not_found(owner, farm):
    # Otra operación la elimina justo después de que se buscó y antes de obtener el bloqueo de
    # la finca: la edición debe responder `not_found`, no un error inesperado.
    plot = PlotFactory(farm=farm)
    lock_farm = rules.lock_farm

    def lock_after_someone_deletes_it(actor, farm_id):
        locked = lock_farm(actor, farm_id)
        Plot.objects.filter(pk=plot.pk).delete()
        return locked

    with mock.patch.object(rules, "lock_farm", side_effect=lock_after_someone_deletes_it):
        with pytest.raises(PlotNotFound):
            update_plot(owner, plot.pk, 1, {"code": "Tarde"})


def test_a_new_boundary_too_far_from_the_farm_point_is_rejected(owner, farm):
    plot = PlotFactory(farm=farm)

    with pytest.raises(PlotTooFarFromFarm):
        update_plot(owner, plot.pk, 1, drawn(rect(0, 20, 1, 21)[:3]))

    plot.refresh_from_db()
    assert plot.boundary is None
    assert plot.version == 1


def test_editing_only_the_area_does_not_look_at_the_distance_again(owner, farm):
    plot = drawn_plot(farm, rect(0, 0, 1, 1))
    # El punto de la finca se movió después de dibujar: la parcela ya dibujada no se rechaza
    # por eso.
    farm.latitude = Decimal("8.5")
    farm.save()

    updated = update_plot(owner, plot.pk, 1, {"code": "Otro código"})

    assert updated.code == "Otro código"
