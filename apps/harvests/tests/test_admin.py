import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.harvests.models import HarvestAuditEvent
from apps.harvests.tests.factories import HarvestFactory, characterized_plot

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


def superuser_client():
    return login(UserFactory(is_staff=True, is_superuser=True))


def test_a_superuser_reads_harvests_and_nobody_edits_them():
    harvest = HarvestFactory()
    client = superuser_client()
    url = reverse("admin:harvests_harvest_change", args=[harvest.pk])

    assert client.get(reverse("admin:harvests_harvest_changelist")).status_code == 200
    assert client.get(url).status_code == 200
    assert client.get(reverse("admin:harvests_harvest_add")).status_code == 403
    assert client.post(url, {}).status_code == 403
    deletion = reverse("admin:harvests_harvest_delete", args=[harvest.pk])
    assert client.post(deletion, {"post": "yes"}).status_code == 403


def test_the_harvest_list_searches_by_the_plot_name():
    wanted = HarvestFactory(plot=characterized_plot(name="La loma buscada"))
    HarvestFactory(plot=characterized_plot(name="Otra parcela"))

    body = (
        superuser_client()
        .get(reverse("admin:harvests_harvest_changelist"), {"q": "buscada"})
        .content.decode()
    )

    assert wanted.plot.name in body
    assert "Otra parcela" not in body


def test_staff_with_the_harvest_permission_does_not_read_them():
    # El admin no filtra por productor: con el permiso de la API vería las cosechas de todos.
    harvest = HarvestFactory()
    client = login(UserFactory(is_staff=True, permissions=["harvests.view_harvest"]))

    assert client.get(reverse("admin:harvests_harvest_changelist")).status_code == 403
    assert (
        client.get(reverse("admin:harvests_harvest_change", args=[harvest.pk])).status_code == 403
    )


def test_a_superuser_reads_the_history_with_its_values():
    harvest = HarvestFactory()
    event = HarvestAuditEvent.record(
        harvest=harvest,
        harvest_ref=harvest.pk,
        plot_ref=harvest.plot_id,
        action="updated",
        version=2,
        changes={"green_weight_kg": {"before": "100.0", "after": "105.5"}},
    )
    client = superuser_client()
    url = reverse("admin:harvests_harvestauditevent_change", args=[event.pk])

    assert client.get(reverse("admin:harvests_harvestauditevent_changelist")).status_code == 200
    assert "green_weight_kg" in client.get(url).content.decode()
    assert client.post(url, {"action": "deleted"}).status_code == 403
