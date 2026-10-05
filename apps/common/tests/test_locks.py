import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.common import locks
from apps.common.exceptions import ApiError
from apps.common.locks import lock_aggregate_root
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.services.audit import record_plot_audit_event
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


class NothingThere(ApiError):
    status_code = 404
    default_detail = "No existe."
    default_code = "not_found"


def lock_plot(plot_id, producer_id):
    return lock_aggregate_root(
        Plot,
        plot_id,
        root="farm",
        scope={"farm__producer_id": producer_id},
        not_found=NothingThere,
    )


def locking_statements(queries):
    return [query["sql"] for query in queries if "FOR UPDATE" in query["sql"]]


def test_it_gives_the_row_and_its_root():
    plot = PlotFactory()

    with transaction.atomic():
        found, root = lock_plot(plot.pk, plot.farm.producer_id)

    assert (found.pk, root.pk) == (plot.pk, plot.farm_id)


def test_only_the_root_is_locked_never_the_row_itself():
    # Con un solo bloqueo no puede haber dos operaciones esperándose entre sí: toda escritura bajo
    # una finca toma el de la finca, y la fila de la parcela no se bloquea aparte.
    plot = PlotFactory()

    with transaction.atomic(), CaptureQueriesContext(connection) as queries:
        lock_plot(plot.pk, plot.farm.producer_id)

    statements = locking_statements(queries)
    assert len(statements) == 1
    assert "farms_farm" in statements[0]


def test_a_row_of_another_producer_is_reported_as_not_found():
    plot = PlotFactory()

    with pytest.raises(NothingThere):
        lock_plot(plot.pk, ProducerFactory().pk)


def test_an_unknown_row_is_not_found():
    with pytest.raises(NothingThere):
        lock_plot("00000000-0000-4000-8000-000000000000", FarmFactory().producer_id)


def test_a_row_deleted_while_waiting_for_the_root_lock_is_not_found():
    plot = PlotFactory()
    lock_root_row = locks.lock_root_row

    def lock_after_someone_deletes_it(*args, **kwargs):
        locked = lock_root_row(*args, **kwargs)
        Plot.objects.filter(pk=plot.pk).delete()
        return locked

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(locks, "lock_root_row", lock_after_someone_deletes_it)
        with transaction.atomic(), pytest.raises(NothingThere):
            lock_plot(plot.pk, plot.farm.producer_id)


def test_the_root_can_be_several_relations_up():
    # Algo que cuelga de la parcela (aquí su historial) llega a la raíz por `plot__farm`.
    plot = PlotFactory()
    event = record_plot_audit_event(plot=plot, actor=None, action=PlotAuditEvent.Action.CREATED)

    with transaction.atomic(), CaptureQueriesContext(connection) as queries:
        found, root = lock_aggregate_root(
            PlotAuditEvent,
            event.pk,
            root="plot__farm",
            scope={"plot__farm__producer_id": plot.farm.producer_id},
            not_found=NothingThere,
        )

    assert (found.pk, root.pk) == (event.pk, plot.farm_id)
    assert len(locking_statements(queries)) == 1
