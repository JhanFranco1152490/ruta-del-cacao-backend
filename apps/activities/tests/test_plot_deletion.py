"""Las actividades no realizadas se van con su parcela; una realizada impide eliminarla, y con
ella a su finca y a su productor. Se prueba por las APIs de esas apps, que no saben nada de las
actividades."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.activities.choices import ActivityStatus
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot
from apps.plots.tests.factories import PlotFactory
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

DELETED = AgriculturalActivityAuditEvent.Action.DELETED


def pending_on(plot, days=3, **kwargs):
    return AgriculturalActivityFactory(
        plot=plot, scheduled_date=today_in_bogota() + timedelta(days=days), **kwargs
    )


def done_on(plot):
    return AgriculturalActivityFactory(
        plot=plot,
        status=ActivityStatus.DONE,
        done_date=today_in_bogota(),
        completed_at=timezone.now(),
    )


def deleted_events(*activity_ids):
    return AgriculturalActivityAuditEvent.objects.filter(
        activity_ref__in=activity_ids, action=DELETED
    ).count()


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner_client(auth_client, producer):
    return auth_client(make_producer_owner(producer))


def test_a_plot_with_pending_activities_is_deleted_with_them(owner_client, producer):
    plot = PlotFactory(farm=FarmFactory(producer=producer))
    scheduled = pending_on(plot)
    overdue = pending_on(plot, days=-5)
    ids = [scheduled.pk, overdue.pk]

    response = owner_client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 204
    assert not AgriculturalActivity.objects.filter(pk__in=ids).exists()
    assert deleted_events(*ids) == 2


def test_a_plot_with_a_done_activity_is_not_deleted(owner_client, producer):
    plot = PlotFactory(farm=FarmFactory(producer=producer))
    pending = pending_on(plot)
    done_on(plot)

    response = owner_client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "plot_has_records"
    assert Plot.objects.filter(pk=plot.pk).exists()
    assert AgriculturalActivity.objects.filter(pk=pending.pk).exists()


def test_a_farm_takes_the_pending_activities_of_its_plots(owner_client, producer):
    farm = FarmFactory(producer=producer)
    activity = pending_on(PlotFactory(farm=farm))
    activity_id = activity.pk

    response = owner_client.delete(f"/api/farms/{farm.pk}?expected_version=1")

    assert response.status_code == 204
    assert not AgriculturalActivity.objects.filter(pk=activity_id).exists()


def test_a_farm_with_a_done_activity_is_not_deleted(owner_client, producer):
    farm = FarmFactory(producer=producer)
    done_on(PlotFactory(farm=farm))

    response = owner_client.delete(f"/api/farms/{farm.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "farm_has_records"
    assert Farm.objects.filter(pk=farm.pk).exists()


def test_a_producer_whose_pending_activity_is_assigned_to_one_of_its_accounts_is_deleted(
    auth_client, producer
):
    # La cuenta nunca inició sesión: se va con el productor. Su actividad pendiente tiene que irse
    # antes que ella, porque el responsable de una actividad está protegido.
    never_signed_in = UserFactory(producer=producer)
    activity = pending_on(
        PlotFactory(farm=FarmFactory(producer=producer)), assignee=never_signed_in
    )
    activity_id = activity.pk
    association = auth_client(make_administrator())

    response = association.delete(f"/api/producers/{producer.pk}?expected_version=1")

    assert response.status_code == 204
    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert not AgriculturalActivity.objects.filter(pk=activity_id).exists()


def test_a_producer_with_a_done_activity_is_not_deleted(auth_client, producer):
    done_on(PlotFactory(farm=FarmFactory(producer=producer)))
    association = auth_client(make_administrator())

    response = association.delete(f"/api/producers/{producer.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "producer_has_records"
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_an_account_responsible_for_an_activity_is_not_deleted(owner_client, producer):
    employee = UserFactory(producer=producer)
    pending_on(PlotFactory(farm=FarmFactory(producer=producer)), assignee=employee)

    response = owner_client.delete(f"/api/users/{employee.pk}")

    assert response.status_code == 409
    assert response.data["code"] == "account_has_activity"
