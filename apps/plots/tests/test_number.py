"""El número consecutivo de cada parcela dentro de su finca (la base del código `P05`)."""

import uuid

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot
from apps.plots.services import create_plot, delete_plot
from apps.plots.tests.factories import PlotFactory, plot_data
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def farm(owner):
    return FarmFactory(producer=owner.producer, area_hectares=100)


def numbers_of(farm):
    return sorted(Plot.objects.filter(farm=farm).values_list("number", flat=True))


def test_plots_of_a_farm_get_consecutive_numbers(owner, farm):
    first, _ = create_plot(owner, plot_data(farm, code="Uno"))
    second, _ = create_plot(owner, plot_data(farm, code="Dos"))

    assert (first.number, second.number) == (1, 2)


def test_each_farm_counts_its_own_plots(owner, farm):
    other = FarmFactory(producer=owner.producer, area_hectares=100)
    create_plot(owner, plot_data(farm, code="Uno"))

    plot, _ = create_plot(owner, plot_data(other, code="Uno"))

    assert plot.number == 1


def test_a_deleted_plot_does_not_free_its_number(owner, farm):
    create_plot(owner, plot_data(farm, code="Uno"))
    mistaken, _ = create_plot(owner, plot_data(farm, code="Dos"))
    delete_plot(owner, mistaken.pk, mistaken.version)

    plot, _ = create_plot(owner, plot_data(farm, code="Tres"))

    assert plot.number == 3


def test_a_resent_plot_does_not_use_another_number(owner, farm):
    data = plot_data(farm, id=uuid.uuid4())
    create_plot(owner, dict(data))

    _, created = create_plot(owner, dict(data))
    plot, _ = create_plot(owner, plot_data(farm, code="Otra"))

    assert created is False
    assert plot.number == 2


def test_a_rejected_plot_does_not_use_a_number(owner, farm):
    create_plot(owner, plot_data(farm, code="Uno"))

    with pytest.raises(Exception):  # noqa: B017 - código repetido
        create_plot(owner, plot_data(farm, code="uno"))
    plot, _ = create_plot(owner, plot_data(farm, code="Dos"))

    assert plot.number == 2


def test_the_factory_takes_the_number_from_the_same_counter(farm):
    assert PlotFactory(farm=farm).number == 1
    assert PlotFactory(farm=farm).number == 2


@pytest.mark.django_db(transaction=True)
def test_simultaneous_plots_of_a_farm_get_different_numbers(owner):
    farm = FarmFactory(producer=owner.producer, area_hectares=100)

    run_in_parallel(lambda n: create_plot(owner, plot_data(farm, code=f"P{n}")), [1, 2, 3, 4])

    assert numbers_of(farm) == [1, 2, 3, 4]
    farm.refresh_from_db()
    assert farm.plot_sequence == 4
