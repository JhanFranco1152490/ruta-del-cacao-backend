from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.notifications.choices import NotificationSeverity
from apps.notifications.models import Notification
from apps.notifications.tests.factories import NotificationFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/notifications"
COUNT_URL = "/api/notifications/unread-count"
VIEW = "activities.view_agriculturalactivity"


@pytest.fixture
def farm():
    return FarmFactory(producer=ProducerFactory())


@pytest.fixture
def owner(farm):
    return make_producer_owner(farm.producer)


def activity_in(farm, days_from_today=-3):
    return AgriculturalActivityFactory(
        plot=PlotFactory(farm=farm),
        scheduled_date=today_in_bogota() + timedelta(days=days_from_today),
    )


def notify(recipient, farm, **kwargs):
    return NotificationFactory(recipient=recipient, activity=activity_in(farm), **kwargs)


def ids(response):
    assert response.status_code == 200, response.data
    return [row["id"] for row in response.data["results"]]


def test_it_needs_a_session(anonymous_client):
    assert anonymous_client.get(LIST_URL).status_code == 401
    assert anonymous_client.get(COUNT_URL).status_code == 401


def test_each_person_sees_only_their_own(auth_client, owner, farm):
    mine = notify(owner, farm)
    notify(make_delegate(farm.producer, [VIEW], farm=farm), farm)

    assert ids(auth_client(owner).get(LIST_URL)) == [str(mine.pk)]


def test_a_notification_looks_like_this(auth_client, owner, farm):
    notification = notify(owner, farm)

    [row] = auth_client(owner).get(LIST_URL).data["results"]

    assert set(row) == {
        "id",
        "kind",
        "severity",
        "created_at",
        "read_at",
        "condition_date",
        "condition_at",
        "resolved_at",
        "detection_id",
        "activity",
        "lot",
        "fermentation_turn",
        "drying_log",
    }
    assert row["kind"] == "activity_overdue"
    assert row["severity"] == "normal"
    assert row["read_at"] is None
    assert row["detection_id"] is None
    assert row["condition_date"] == str(notification.condition_date)
    # Lo de un lote va vacío en un aviso de actividad.
    assert [row[name] for name in ("condition_at", "resolved_at", "lot")] == [None, None, None]
    assert [row[name] for name in ("fermentation_turn", "drying_log")] == [None, None]


def test_the_activity_comes_as_it_is_today(auth_client, owner, farm):
    notification = notify(owner, farm)

    activity = auth_client(owner).get(LIST_URL).data["results"][0]["activity"]

    # La misma forma del calendario: el estado y los días de retraso son los de hoy.
    assert activity["id"] == str(notification.activity_id)
    assert activity["state"] == "overdue"
    assert activity["days_late"] == 3
    assert activity["plot"]["farm"]["name"] == farm.name


def test_dismissed_ones_are_not_listed(auth_client, owner, farm):
    notify(owner, farm, dismissed_at=timezone.now())

    assert ids(auth_client(owner).get(LIST_URL)) == []


def test_without_permission_to_see_activities_the_inbox_is_empty(auth_client, farm):
    seller = make_delegate(farm.producer, ["farms.view_farm"], farm=farm)
    notify(seller, farm)

    assert ids(auth_client(seller).get(LIST_URL)) == []
    assert auth_client(seller).get(COUNT_URL).data == {"count": 0}


def test_an_employee_sees_only_what_is_in_the_farms_it_reaches_today(auth_client, farm):
    other_farm = FarmFactory(producer=farm.producer)
    employee = make_delegate(farm.producer, [VIEW], farm=farm)
    kept = notify(employee, farm)
    moved = notify(employee, other_farm)
    client = auth_client(employee)

    assert ids(client.get(LIST_URL)) == [str(kept.pk)]

    employee.farms.add(other_farm)

    assert set(ids(client.get(LIST_URL))) == {str(kept.pk), str(moved.pk)}


def test_newest_first(auth_client, owner, farm):
    old = notify(owner, farm)
    new = notify(owner, farm)
    Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))

    assert ids(auth_client(owner).get(LIST_URL)) == [str(new.pk), str(old.pk)]


def test_unread_critical_ones_go_first(auth_client, owner, farm):
    critical = notify(owner, farm, severity=NotificationSeverity.CRITICAL)
    normal = notify(owner, farm)
    Notification.objects.filter(pk=critical.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )

    assert ids(auth_client(owner).get(LIST_URL)) == [str(critical.pk), str(normal.pk)]


def test_a_read_critical_one_goes_back_to_its_date(auth_client, owner, farm):
    critical = notify(owner, farm, severity=NotificationSeverity.CRITICAL, read_at=timezone.now())
    normal = notify(owner, farm)
    Notification.objects.filter(pk=critical.pk).update(
        created_at=timezone.now() - timedelta(days=2)
    )

    assert ids(auth_client(owner).get(LIST_URL)) == [str(normal.pk), str(critical.pk)]


def test_pages_do_not_repeat_or_skip_rows_with_the_same_time(auth_client, owner, farm):
    made = [notify(owner, farm) for _ in range(25)]
    Notification.objects.filter(pk__in=[n.pk for n in made]).update(created_at=timezone.now())
    client = auth_client(owner)

    first = ids(client.get(LIST_URL))
    second = ids(client.get(LIST_URL, {"page": 2}))

    assert len(first) == 20
    assert set(first) | set(second) == {str(n.pk) for n in made}
    assert not set(first) & set(second)


def test_only_unread_ones_when_asked(auth_client, owner, farm):
    unread = notify(owner, farm)
    notify(owner, farm, read_at=timezone.now())

    assert ids(auth_client(owner).get(LIST_URL, {"unread": "true"})) == [str(unread.pk)]


def test_the_unread_count_leaves_out_read_dismissed_and_unreachable(auth_client, farm):
    employee = make_delegate(farm.producer, [VIEW], farm=farm)
    notify(employee, farm)
    notify(employee, farm)
    notify(employee, farm, read_at=timezone.now())
    notify(employee, farm, dismissed_at=timezone.now())
    notify(employee, FarmFactory(producer=farm.producer))
    notify(UserFactory(producer=farm.producer), farm)

    assert auth_client(employee).get(COUNT_URL).data == {"count": 2}


def test_listing_twenty_takes_the_same_queries_as_one(
    auth_client, owner, farm, django_assert_max_num_queries
):
    notify(owner, farm)
    client = auth_client(owner)
    with django_assert_max_num_queries(50) as one:
        client.get(LIST_URL)
    for _ in range(19):
        notify(owner, farm)

    with django_assert_max_num_queries(len(one.captured_queries)):
        response = client.get(LIST_URL)

    assert len(response.data["results"]) == 20
