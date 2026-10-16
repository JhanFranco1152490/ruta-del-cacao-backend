import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.activities.services.create import create_activity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import make_assignee
from apps.plots.tests.factories import PlotFactory

from .factories import AgriculturalActivityFactory, AgriculturalActivityInputFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def event():
    plot = PlotFactory()
    owner = make_assignee(plot.farm.producer)
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


# --- Actividades ---


def test_an_activity_shows_the_inputs_it_used_and_nothing_can_be_edited():
    used = AgriculturalActivityInputFactory()
    activity = used.activity
    client = login(UserFactory(is_staff=True, is_superuser=True))
    url = reverse("admin:activities_agriculturalactivity_change", args=[activity.pk])

    body = client.get(url).content.decode()

    assert used.input.name in body
    assert (
        client.get(reverse("admin:activities_agriculturalactivity_changelist")).status_code == 200
    )
    assert client.get(reverse("admin:activities_agriculturalactivity_add")).status_code == 403
    assert client.post(url, {}).status_code == 403
    deletion = reverse("admin:activities_agriculturalactivity_delete", args=[activity.pk])
    assert client.post(deletion, {"post": "yes"}).status_code == 403


def test_the_activity_list_searches_by_plot_code():
    wanted = AgriculturalActivityFactory(plot__name="P-BUSCADA")
    AgriculturalActivityFactory(plot__name="P-OTRA")
    client = login(UserFactory(is_staff=True, is_superuser=True))

    body = client.get(
        reverse("admin:activities_agriculturalactivity_changelist"), {"q": "P-BUSCADA"}
    ).content.decode()

    assert wanted.plot.name in body and "P-OTRA" not in body


def test_staff_who_is_not_the_technical_account_does_not_read_activities():
    activity = AgriculturalActivityFactory()
    employee = login(
        UserFactory(
            is_staff=True,
            producer=activity.plot.farm.producer,
            permissions=["activities.view_agriculturalactivity"],
        )
    )

    assert (
        employee.get(reverse("admin:activities_agriculturalactivity_changelist")).status_code
        == 403
    )
