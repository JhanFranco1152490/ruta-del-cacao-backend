import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.activities.services.create import create_activity
from apps.activities.state import today_in_bogota
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def event():
    plot = PlotFactory()
    owner = UserFactory(producer=plot.farm.producer)
    activity, _ = create_activity(
        owner,
        {
            "plot_id": plot.pk,
            "activity_type": "fertilization",
            "scheduled_date": today_in_bogota(),
            "assignee_id": owner.pk,
        },
    )
    return activity.audit_events.get()


def changelist_url():
    return reverse("admin:activities_agriculturalactivityauditevent_changelist")


def change_url(event):
    return reverse("admin:activities_agriculturalactivityauditevent_change", args=[event.pk])


def test_a_superuser_reads_the_history_with_its_values(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    listing = client.get(changelist_url())
    detail = client.get(change_url(event))

    assert listing.status_code == 200
    assert detail.status_code == 200
    assert "fertilization" in detail.content.decode()


def test_staff_with_the_activity_permission_does_not_read_the_history(event):
    # El admin no filtra por productor: con el permiso de la API vería las actividades de todos.
    client = login(
        UserFactory(is_staff=True, permissions=["activities.view_agriculturalactivity"])
    )

    assert client.get(changelist_url()).status_code == 403
    assert client.get(change_url(event)).status_code == 403


def test_nobody_edits_the_history_from_the_admin(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    response = client.post(change_url(event), {"action": "deleted"})

    assert response.status_code == 403
