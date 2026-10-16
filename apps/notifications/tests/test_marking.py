from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.helpers import open_session
from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.notifications.models import Notification
from apps.notifications.services.evaluate import evaluate_alerts
from apps.notifications.tests.factories import NotificationFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

VIEW = "activities.view_agriculturalactivity"


@pytest.fixture
def farm():
    return FarmFactory(producer=ProducerFactory())


@pytest.fixture
def owner(farm):
    return make_producer_owner(farm.producer)


def notify(recipient, farm, **kwargs):
    activity = AgriculturalActivityFactory(
        plot=PlotFactory(farm=farm), scheduled_date=today_in_bogota() - timedelta(days=3)
    )
    return NotificationFactory(recipient=recipient, activity=activity, **kwargs)


def fresh(notification):
    notification.refresh_from_db()
    return notification


def count(client):
    return client.get("/api/notifications/unread-count").data["count"]


# Marcar como leída.


def test_reading_one_marks_it(auth_client, owner, farm):
    notification = notify(owner, farm)
    client = auth_client(owner)

    response = client.post(f"/api/notifications/{notification.pk}/read")

    assert response.status_code == 204
    assert fresh(notification).read_at is not None
    assert count(client) == 0


def test_reading_it_again_keeps_when_it_was_first_read(auth_client, owner, farm):
    read_at = timezone.now() - timedelta(hours=5)
    notification = notify(owner, farm, read_at=read_at)

    response = auth_client(owner).post(f"/api/notifications/{notification.pk}/read")

    assert response.status_code == 204
    assert fresh(notification).read_at == read_at


def test_reading_all_of_them(auth_client, owner, farm):
    unread = [notify(owner, farm) for _ in range(3)]
    notify(owner, farm, read_at=timezone.now())
    notify(owner, FarmFactory(producer=farm.producer), dismissed_at=timezone.now())
    client = auth_client(owner)

    response = client.post("/api/notifications/read-all")

    assert response.status_code == 200
    assert response.data == {"updated": 3}
    assert all(fresh(n).read_at for n in unread)
    assert count(client) == 0


def test_read_all_leaves_what_the_account_does_not_see(auth_client, farm):
    employee = make_delegate(farm.producer, [VIEW], farm=farm)
    elsewhere = notify(employee, FarmFactory(producer=farm.producer))

    assert auth_client(employee).post("/api/notifications/read-all").data == {"updated": 0}
    assert fresh(elsewhere).read_at is None


# Eliminar y deshacer.


def test_dismissing_one_hides_it(auth_client, owner, farm):
    notification = notify(owner, farm)
    client = auth_client(owner)

    response = client.delete(f"/api/notifications/{notification.pk}")

    assert response.status_code == 204
    assert fresh(notification).dismissed_at is not None
    assert client.get("/api/notifications").data["results"] == []
    assert count(client) == 0


def test_dismissing_it_again_is_fine(auth_client, owner, farm):
    notification = notify(owner, farm, dismissed_at=timezone.now())

    assert auth_client(owner).delete(f"/api/notifications/{notification.pk}").status_code == 204


def test_a_dismissed_one_cannot_be_read(auth_client, owner, farm):
    notification = notify(owner, farm, dismissed_at=timezone.now())

    response = auth_client(owner).post(f"/api/notifications/{notification.pk}/read")

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_undo_brings_it_back(auth_client, owner, farm):
    notification = notify(owner, farm, dismissed_at=timezone.now())
    client = auth_client(owner)

    response = client.post(f"/api/notifications/{notification.pk}/restore")

    assert response.status_code == 204
    assert fresh(notification).dismissed_at is None
    assert count(client) == 1


def test_dismissing_the_read_ones(auth_client, owner, farm):
    read = [notify(owner, farm, read_at=timezone.now()) for _ in range(2)]
    unread = notify(owner, farm)

    response = auth_client(owner).post("/api/notifications/dismiss-read")

    assert response.status_code == 200
    assert response.data == {"dismissed": 2}
    assert all(fresh(n).dismissed_at for n in read)
    assert fresh(unread).dismissed_at is None


def test_a_dismissed_overdue_does_not_come_back(auth_client, owner, farm):
    activity = AgriculturalActivityFactory(
        plot=PlotFactory(farm=farm),
        assignee=owner,
        scheduled_date=today_in_bogota() - timedelta(days=3),
    )
    evaluate_alerts(today_in_bogota(), timezone.now())
    notification = Notification.objects.get(activity=activity, recipient=owner)
    client = auth_client(owner)
    client.delete(f"/api/notifications/{notification.pk}")

    evaluate_alerts(today_in_bogota(), timezone.now())

    assert client.get("/api/notifications").data["results"] == []


# Lo ajeno y la seguridad.


@pytest.mark.parametrize(
    "method, path",
    [("post", "{}/read"), ("delete", "{}"), ("post", "{}/restore")],
)
def test_someone_elses_notification_does_not_exist(auth_client, owner, farm, method, path):
    theirs = notify(make_delegate(farm.producer, [VIEW], farm=farm), farm)

    response = getattr(auth_client(owner), method)("/api/notifications/" + path.format(theirs.pk))

    assert (response.status_code, response.data["code"]) == (404, "not_found")
    assert fresh(theirs).read_at is None
    assert fresh(theirs).dismissed_at is None


def test_one_from_a_farm_it_no_longer_reaches_does_not_exist(auth_client, farm):
    employee = make_delegate(farm.producer, [VIEW], farm=farm)
    elsewhere = notify(employee, FarmFactory(producer=farm.producer))

    response = auth_client(employee).post(f"/api/notifications/{elsewhere.pk}/read")

    assert response.status_code == 404


def test_writing_needs_the_csrf_token(owner, farm):
    notification = notify(owner, farm)
    # Con la sesión en las cookies pero sin el token de CSRF, como un sitio ajeno.
    client = open_session(APIClient(enforce_csrf_checks=True), owner)

    for response in (
        client.post(f"/api/notifications/{notification.pk}/read"),
        client.post("/api/notifications/read-all"),
        client.delete(f"/api/notifications/{notification.pk}"),
        client.post("/api/notifications/dismiss-read"),
    ):
        assert response.status_code == 403
    assert fresh(notification).read_at is None
    assert fresh(notification).dismissed_at is None


def test_it_needs_a_session(anonymous_client, owner, farm):
    notification = notify(owner, farm)

    response = anonymous_client.post(f"/api/notifications/{notification.pk}/read")

    assert (response.status_code, response.data["code"]) == (401, "not_authenticated")
    assert fresh(notification).read_at is None
