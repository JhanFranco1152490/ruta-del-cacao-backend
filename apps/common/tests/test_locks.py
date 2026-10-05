import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.common import locks
from apps.common.exceptions import ApiError
from apps.common.locks import lock_plot_of_producer
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


class NothingThere(ApiError):
    status_code = 404
    default_detail = "No existe."
    default_code = "not_found"


def lock(plot_id, producer_id):
    return lock_plot_of_producer(
        Plot, producer_id=producer_id, plot_id=plot_id, not_found=NothingThere
    )


def test_it_gives_the_plot_with_its_farm_loaded():
    plot = PlotFactory()

    with transaction.atomic():
        locked = lock(plot.pk, plot.farm.producer_id)

    assert locked.pk == plot.pk
    # La finca ya viene cargada: quien llama no paga otra consulta para leerla.
    with CaptureQueriesContext(connection) as queries:
        assert locked.farm.pk == plot.farm_id
    assert len(queries) == 0


def test_the_farm_is_locked_before_the_plot():
    # Dos operaciones que toman los mismos bloqueos en orden distinto pueden esperarse una a la
    # otra: todas toman la finca primero.
    plot = PlotFactory()

    with transaction.atomic(), CaptureQueriesContext(connection) as queries:
        lock(plot.pk, plot.farm.producer_id)

    locking = [query["sql"] for query in queries if "FOR UPDATE" in query["sql"]]
    assert len(locking) == 2
    assert "farms_farm" in locking[0] and "plots_plot" in locking[1]


def test_a_plot_of_another_producer_is_reported_as_not_found():
    plot = PlotFactory()

    with pytest.raises(NothingThere):
        lock(plot.pk, ProducerFactory().pk)


def test_an_unknown_plot_is_not_found():
    with pytest.raises(NothingThere):
        lock("00000000-0000-4000-8000-000000000000", FarmFactory().producer_id)


def test_a_plot_deleted_while_waiting_for_the_farm_lock_is_not_found():
    plot = PlotFactory()
    real_lock = locks.lock_farm_row

    def lock_after_someone_deletes_it(*args, **kwargs):
        locked = real_lock(*args, **kwargs)
        Plot.objects.filter(pk=plot.pk).delete()
        return locked

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(locks, "lock_farm_row", lock_after_someone_deletes_it)
        with transaction.atomic(), pytest.raises(NothingThere):
            lock(plot.pk, plot.farm.producer_id)


def test_lock_farm_row_is_limited_to_the_producer():
    farm = FarmFactory()

    with transaction.atomic():
        assert locks.lock_farm_row(type(farm), producer_id=farm.producer_id, farm_id=farm.pk)
        assert not locks.lock_farm_row(
            type(farm), producer_id=ProducerFactory().pk, farm_id=farm.pk
        )
