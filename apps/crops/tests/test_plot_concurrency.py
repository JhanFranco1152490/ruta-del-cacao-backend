"""Guardar una ficha toma los bloqueos en el mismo orden que las operaciones de parcelas (finca y
después parcela): las dos a la vez terminan una detrás de la otra, sin trabarse."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.crops.exceptions import PlotInactive, PlotNotFound
from apps.crops.models import PlotCharacterization
from apps.crops.services import save_characterization
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.plots.exceptions import PlotHasRecords
from apps.plots.models import Plot
from apps.plots.services import delete_plot, update_plot
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


def attempt(action):
    """El resultado de la acción, o la excepción que lanzó, para comparar lo que pasó en cada
    hilo."""
    try:
        return action()
    except Exception as error:  # noqa: BLE001
        return error


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def plot(owner):
    return PlotFactory(farm__producer=owner.producer, farm__area_hectares=Decimal("12.50"))


@pytest.fixture
def characterize(owner, plot):
    variety = CacaoVarietyFactory()
    content = {
        "plantings": [
            {
                "variety_id": variety.pk,
                "planting_date": date(2021, 3, 1),
                "tree_count": 900,
                "propagation": "grafted",
                "stage": "full_production",
            }
        ],
        "management_system": None,
        "shade_type": None,
        "captured_at": None,
    }
    return lambda: save_characterization(owner, plot.pk, None, content)


def run_together(first, second):
    return run_in_parallel(lambda action: attempt(action), [first, second])


def test_a_characterization_and_a_plot_edit_both_finish(owner, plot, characterize):
    edit = lambda: update_plot(owner, plot.pk, 1, {"area_hectares": Decimal("2.00")})  # noqa: E731

    saved, edited = run_together(characterize, edit)

    assert isinstance(saved, tuple), saved
    assert isinstance(edited, Plot), edited
    assert PlotCharacterization.objects.filter(pk=plot.pk).exists()
    assert Plot.objects.get(pk=plot.pk).area_hectares == Decimal("2.00")


def test_a_characterization_and_a_deactivation_end_consistent(owner, plot, characterize):
    deactivate = lambda: update_plot(owner, plot.pk, 1, {"is_active": False})  # noqa: E731

    saved, deactivated = run_together(characterize, deactivate)

    assert isinstance(deactivated, Plot), deactivated
    # Si la desactivación ganó, la ficha ya no se puede registrar; si no, quedó registrada antes.
    if isinstance(saved, PlotInactive):
        assert not PlotCharacterization.objects.exists()
    else:
        assert isinstance(saved, tuple), saved
        assert PlotCharacterization.objects.filter(pk=plot.pk).exists()


def test_a_characterization_and_a_deletion_never_leave_an_orphan(owner, plot, characterize):
    delete = lambda: delete_plot(owner, plot.pk, 1)  # noqa: E731

    saved, deleted = run_together(characterize, delete)

    if isinstance(deleted, PlotHasRecords):
        # La ficha llegó primero: la parcela se queda, con su ficha.
        assert isinstance(saved, tuple), saved
        assert PlotCharacterization.objects.filter(pk=plot.pk).exists()
    else:
        # El borrado llegó primero: la ficha ya no tiene parcela que caracterizar.
        assert deleted is None, deleted
        assert isinstance(saved, PlotNotFound), saved
        assert not Plot.objects.filter(pk=plot.pk).exists()
        assert not PlotCharacterization.objects.exists()
