import uuid
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.tests.factories import FarmFactory
from apps.plots.exceptions import PlotAreaExceedsFarm, PlotOverlap
from apps.plots.geometry import measured_area_hectares, to_polygon, validate_boundary
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.services import create_plot
from apps.plots.tests.factories import plot_data, rect
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


def attempt(action):
    """El resultado de la acción, o la excepción que lanzó, para comparar lo que pasó en cada
    hilo."""
    try:
        return action()
    except Exception as error:  # noqa: BLE001
        return error


def test_two_plots_that_together_exceed_the_farm_area_cannot_both_be_saved(owner):
    # Dos teléfonos sin conexión registran 3 ha cada uno en una finca con 4 ha libres.
    farm = FarmFactory(producer=owner.producer, area_hectares=Decimal("4.00"))

    results = run_in_parallel(
        lambda code: attempt(
            lambda: create_plot(owner, plot_data(farm, code=code, area_hectares=Decimal("3.00")))
        ),
        ["P-01", "P-02"],
    )

    errors = [result for result in results if not isinstance(result, tuple)]
    assert len(errors) == 1 and isinstance(errors[0], PlotAreaExceedsFarm)
    assert Plot.objects.count() == 1


def test_two_overlapping_plots_cannot_both_be_saved(owner):
    farm = FarmFactory(producer=owner.producer, area_hectares=Decimal("50.00"))
    boundaries = {"P-01": rect(0, 0, 2, 1), "P-02": rect(1, 0, 3, 1)}

    def create(code):
        vertices = boundaries[code]
        area = measured_area_hectares(to_polygon(validate_boundary(vertices).vertices))
        data = plot_data(
            farm, code=code, boundary=vertices, area_hectares=area.quantize(Decimal("0.01"))
        )
        return attempt(lambda: create_plot(owner, data))

    results = run_in_parallel(create, list(boundaries))

    errors = [result for result in results if not isinstance(result, tuple)]
    assert len(errors) == 1 and isinstance(errors[0], PlotOverlap)
    assert Plot.objects.count() == 1


def test_two_simultaneous_syncs_of_the_same_plot_create_it_once(owner):
    farm = FarmFactory(producer=owner.producer)
    data = plot_data(farm, id=uuid.uuid4())

    results = run_in_parallel(lambda _: create_plot(owner, dict(data)), [1, 2])

    assert sorted(created for _, created in results) == [False, True]
    assert Plot.objects.count() == 1
    assert PlotAuditEvent.objects.count() == 1
