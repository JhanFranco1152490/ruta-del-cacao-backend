from datetime import date

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.crops.exceptions import StaleCharacterizationVersion
from apps.crops.models import PlotCharacterization, PlotCharacterizationAuditEvent
from apps.crops.services import save_characterization
from apps.crops.tests.factories import CacaoVarietyFactory
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


def content(variety, tree_count) -> dict:
    return {
        "varieties": [{"variety_id": variety.pk, "tree_count": tree_count}],
        "planting_date": date(2021, 3, 1),
        "stage": "full_production",
        "management_system": None,
        "shade_type": None,
        "captured_at": None,
    }


def test_two_phones_registering_the_same_plot_end_with_one_saved_and_one_stale():
    owner = UserFactory(producer=ProducerFactory())
    plot = PlotFactory(farm__producer=owner.producer)
    variety = CacaoVarietyFactory()

    results = run_in_parallel(
        lambda trees: attempt(
            lambda: save_characterization(owner, plot.pk, None, content(variety, trees))
        ),
        [900, 1200],
    )

    saved = [result for result in results if isinstance(result, tuple)]
    stale = [result for result in results if isinstance(result, StaleCharacterizationVersion)]
    assert len(saved) == 1 and len(stale) == 1
    winner = saved[0][0]
    assert stale[0].current_characterization.pk == winner.pk
    assert PlotCharacterization.objects.get().version == 1
    assert PlotCharacterizationAuditEvent.objects.count() == 1


def test_two_retries_of_the_same_registration_save_it_once():
    owner = UserFactory(producer=ProducerFactory())
    plot = PlotFactory(farm__producer=owner.producer)
    variety = CacaoVarietyFactory()

    results = run_in_parallel(
        lambda _: attempt(
            lambda: save_characterization(owner, plot.pk, None, content(variety, 900))
        ),
        [1, 2],
    )

    assert all(isinstance(result, tuple) for result in results)
    assert sorted(created for _, created in results) == [False, True]
    assert PlotCharacterizationAuditEvent.objects.count() == 1
