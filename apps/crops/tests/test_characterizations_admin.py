from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.crops.models import PlotCharacterizationAuditEvent
from apps.crops.services import save_characterization
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("plain_static_files", "empty_catalog"),
]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def event():
    owner = UserFactory(producer=ProducerFactory())
    plot = PlotFactory(farm__producer=owner.producer)
    variety = CacaoVarietyFactory(name="CCN-51")
    save_characterization(
        owner,
        plot.pk,
        None,
        {
            "plantings": [
                {
                    "variety_id": variety.pk,
                    "planting_date": date(2021, 3, 1),
                    "tree_count": 1800,
                    "propagation": "grafted",
                    "stage": "renovation",
                }
            ],
            "management_system": None,
            "shade_type": None,
            "captured_at": None,
        },
    )
    return PlotCharacterizationAuditEvent.objects.get()


def changelist_url():
    return reverse("admin:crops_plotcharacterizationauditevent_changelist")


def change_url(event):
    return reverse("admin:crops_plotcharacterizationauditevent_change", args=[event.pk])


def test_a_superuser_reads_the_history_with_its_values(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    listing = client.get(changelist_url())
    detail = client.get(change_url(event))

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert "renovation" in detail.content.decode()
    assert "CCN-51" in detail.content.decode()


def test_staff_with_the_plot_permission_does_not_read_the_history(event):
    # El admin no filtra por productor: con el permiso de la API vería las fichas de todos.
    client = login(UserFactory(is_staff=True, permissions=["plots.view_plot"]))

    assert client.get(changelist_url()).status_code == 403
    assert client.get(change_url(event)).status_code == 403


def test_the_history_cannot_be_changed_from_the_admin(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    add = client.get(reverse("admin:crops_plotcharacterizationauditevent_add"))
    change = client.post(change_url(event), {"action": "updated"})
    delete = client.post(
        reverse("admin:crops_plotcharacterizationauditevent_delete", args=[event.pk]),
        {"post": "yes"},
    )

    assert add.status_code == 403
    assert change.status_code == 403
    assert delete.status_code == 403
    assert PlotCharacterizationAuditEvent.objects.get().action == "created"
