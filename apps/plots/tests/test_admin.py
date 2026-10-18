from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import done_activity
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot, PlotAuditEvent

from .factories import PlotFactory, boundary_fields, rect

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def client(superuser):
    return login(superuser)


def changelist_url():
    return reverse("admin:plots_plot_changelist")


def change_url(plot):
    return reverse("admin:plots_plot_change", args=[plot.pk])


def delete_url(plot):
    return reverse("admin:plots_plot_delete", args=[plot.pk])


def form_data(plot, **overrides):
    data = {
        "code": plot.code,
        "area_hectares": str(plot.area_hectares),
        "is_active": "on" if plot.is_active else "",
        "expected_version": plot.version,
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


def test_the_list_shows_the_plot_with_its_farm_and_producer_and_searches_them(client):
    plot = PlotFactory(name="P-LOTE", farm=FarmFactory(name="Finca El Pórtico"))
    PlotFactory(name="P-OTRO")

    by_farm = client.get(changelist_url(), {"q": "portico"}).content.decode()
    by_producer = client.get(
        changelist_url(), {"q": plot.farm.producer.member_code}
    ).content.decode()

    assert "P-LOTE" in by_farm and "P-OTRO" not in by_farm
    assert "P-LOTE" in by_producer and "P-OTRO" not in by_producer


def test_saving_goes_through_the_service_and_leaves_the_history_with_the_admin_as_actor(
    client, superuser
):
    plot = PlotFactory(name="P-01")

    response = client.post(change_url(plot), form_data(plot, name="P-01 Alta"))

    assert response.status_code == 302
    plot.refresh_from_db()
    assert (plot.name, plot.version) == ("P-01 Alta", 2)
    event = PlotAuditEvent.objects.get(plot=plot, action=PlotAuditEvent.Action.UPDATED)
    assert event.actor == superuser


def test_deactivating_is_a_status_change_in_the_history(client):
    plot = PlotFactory()

    client.post(change_url(plot), form_data(plot, is_active=""))

    plot.refresh_from_db()
    assert not plot.is_active
    assert PlotAuditEvent.objects.filter(
        plot=plot, action=PlotAuditEvent.Action.STATUS_CHANGED
    ).exists()


def test_the_boundary_and_the_farm_cannot_be_changed_from_the_form(client):
    farm = FarmFactory()
    plot = PlotFactory(farm=farm, **boundary_fields(rect(-72.5123, 7.8234, -72.5113, 7.8244)))
    boundary = plot.boundary

    client.post(
        change_url(plot),
        form_data(plot, boundary="[]", farm=FarmFactory().pk, measured_area_hectares="99"),
    )

    plot.refresh_from_db()
    assert (plot.farm_id, plot.boundary) == (farm.pk, boundary)
    assert plot.measured_area_hectares != Decimal("99")


def test_the_change_page_shows_the_measured_area_and_the_boundary_as_read_only(client):
    plot = PlotFactory(**boundary_fields(rect(-72.5123, 7.8234, -72.5113, 7.8244)))

    body = client.get(change_url(plot)).content.decode()

    assert 'name="boundary"' not in body
    assert "field-measured_area_hectares" in body


def test_a_stale_form_is_rejected_and_changes_nothing(client):
    plot = PlotFactory(name="P-01")
    stale = form_data(plot, name="Tardío")
    Plot.objects.filter(pk=plot.pk).update(version=2)

    response = client.post(change_url(plot), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    plot.refresh_from_db()
    assert (plot.name, plot.version) == ("P-01", 2)


def test_an_area_the_farm_cannot_give_is_refused_with_the_services_message(client):
    farm = FarmFactory(area_hectares=Decimal("5.00"))
    plot = PlotFactory(farm=farm, area_hectares=Decimal("1.00"))

    response = client.post(change_url(plot), form_data(plot, area_hectares="9.00"), follow=True)

    assert "supera el área disponible de la finca" in response.content.decode()
    plot.refresh_from_db()
    assert (plot.area_hectares, plot.version) == (Decimal("1.00"), 1)


def test_a_repeated_name_is_refused_with_the_services_message(client):
    farm = FarmFactory()
    plot = PlotFactory(farm=farm, name="P-01")
    PlotFactory(farm=farm, name="P-02")

    response = client.post(change_url(plot), form_data(plot, name="P-02"), follow=True)

    assert "Ya existe una parcela con este nombre" in response.content.decode()
    plot.refresh_from_db()
    assert plot.version == 1


def test_nobody_can_add_plots_from_the_admin(client):
    assert client.get(reverse("admin:plots_plot_add")).status_code == 403


def test_a_plot_created_by_mistake_is_deleted_through_the_service_and_leaves_its_trace(
    client, superuser
):
    plot = PlotFactory()

    response = client.post(delete_url(plot), {"post": "yes"})

    assert response.status_code == 302
    assert not Plot.objects.filter(pk=plot.pk).exists()
    event = PlotAuditEvent.objects.get(plot_ref=plot.pk, action=PlotAuditEvent.Action.DELETED)
    assert event.actor == superuser


def test_a_plot_with_records_is_not_deleted_and_the_admin_says_why(client):
    plot = PlotFactory()
    done_activity(plot=plot)

    response = client.post(delete_url(plot), {"post": "yes"}, follow=True)

    assert Plot.objects.filter(pk=plot.pk).exists()
    assert "tiene registros asociados" in response.content.decode()


def test_the_bulk_delete_action_is_not_offered(client):
    PlotFactory()

    assert "delete_selected" not in client.get(changelist_url()).content.decode()


def test_staff_who_is_not_the_technical_account_only_reaches_its_own_producers_plots():
    mine = PlotFactory(name="P-MIA")
    theirs = PlotFactory(name="P-AJENA")
    staff = UserFactory(
        is_staff=True,
        producer=mine.farm.producer,
        permissions=["plots.view_plot", "plots.change_plot"],
    )
    client = login(staff)

    body = client.get(changelist_url()).content.decode()

    assert "P-MIA" in body and "P-AJENA" not in body
    assert client.get(change_url(theirs)).status_code == 302


def test_the_history_is_read_only_and_only_for_the_superuser(client):
    plot = PlotFactory()
    client.post(change_url(plot), form_data(plot, name="P-NUEVO"))
    event = PlotAuditEvent.objects.get(action=PlotAuditEvent.Action.UPDATED)
    url = reverse("admin:plots_plotauditevent_change", args=[event.pk])

    assert client.get(reverse("admin:plots_plotauditevent_changelist")).status_code == 200
    assert client.get(url).status_code == 200
    assert client.get(reverse("admin:plots_plotauditevent_add")).status_code == 403
    assert client.post(url, {}).status_code == 403
    deletion = reverse("admin:plots_plotauditevent_delete", args=[event.pk])
    assert client.post(deletion, {"post": "yes"}).status_code == 403

    staff = login(UserFactory(is_staff=True, permissions=["plots.view_plot"]))
    assert staff.get(reverse("admin:plots_plotauditevent_changelist")).status_code == 403
