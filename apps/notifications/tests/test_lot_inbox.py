"""Los avisos de un lote en la bandeja: quién los ve y cómo llegan."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.drying.tests.factories import DryingLogEntryFactory, DryingProcessFactory
from apps.farms.tests.factories import FarmFactory
from apps.fermentation.tests.factories import FermentationProcessFactory, FermentationTurnFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.notifications.choices import NotificationKind, NotificationSeverity
from apps.notifications.tests.factories import LotNotificationFactory, NotificationFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/notifications"
COUNT_URL = "/api/notifications/unread-count"
LOTS = "lots.view_lot"
ACTIVITIES = "activities.view_agriculturalactivity"


def lot_on(farm, status):
    return LotFactory(harvest=HarvestFactory(plot=characterized_plot(farm=farm)), status=status)


def fermenting_on(farm):
    return FermentationProcessFactory(lot=lot_on(farm, LotStatus.FERMENTING))


@pytest.fixture
def process():
    return FermentationProcessFactory()


@pytest.fixture
def farm(process):
    return process.lot.harvest.plot.farm


@pytest.fixture
def owner(farm):
    return make_producer_owner(farm.producer)


def listed(client):
    response = client.get(LIST_URL)
    assert response.status_code == 200, response.data
    return response.data["results"]


def ids(client):
    return [row["id"] for row in listed(client)]


# Cómo llega un aviso de lote.


def test_a_pending_turn_comes_with_its_lot_as_it_is_now(auth_client, owner, process, farm):
    due_at = timezone.now() - timedelta(hours=1)
    LotNotificationFactory(lot=process.lot, recipient=owner, condition_at=due_at)

    (row,) = listed(auth_client(owner))

    assert row["kind"] == NotificationKind.FERMENTATION_TURN_DUE
    assert row["activity"] is None
    assert row["condition_at"] == timezone.localtime(due_at).isoformat()
    assert row["resolved_at"] is None
    assert row["fermentation_turn"] is None
    assert row["drying_log"] is None
    lot = row["lot"]
    assert lot["id"] == str(process.lot.pk)
    assert lot["code"] == process.lot.code
    assert lot["status"] == LotStatus.FERMENTING
    assert lot["farm"] == {"id": str(farm.pk), "name": farm.name}
    assert lot["fermentation"]["facility"] == process.facility.name
    assert lot["drying"] is None


def test_a_resolved_one_says_when(auth_client, owner, process):
    resolved_at = timezone.now()
    LotNotificationFactory(lot=process.lot, recipient=owner, resolved_at=resolved_at)

    (row,) = listed(auth_client(owner))

    assert row["resolved_at"] == timezone.localtime(resolved_at).isoformat()


def test_a_fermentation_deviation_comes_with_its_turn_as_it_is_now(auth_client, owner, process):
    FermentationTurnFactory(process=process)
    turn = FermentationTurnFactory(
        process=process, temperature_c=Decimal("53.0"), ph=Decimal("6.10")
    )
    LotNotificationFactory(
        lot=process.lot,
        recipient=owner,
        kind=NotificationKind.FERMENTATION_TEMPERATURE_HIGH,
        fermentation_turn=turn,
        condition_key=f"{turn.pk}:high",
    )
    # Una corrección después del aviso: la bandeja muestra el valor de ahora.
    turn.temperature_c = Decimal("52.5")
    turn.save(update_fields=["temperature_c"])

    (row,) = listed(auth_client(owner))

    assert row["fermentation_turn"] == {
        "id": str(turn.pk),
        "number": 2,
        "turned_at": timezone.localtime(turn.turned_at).isoformat(),
        "temperature_c": "52.5",
        "ph": "6.10",
    }


def test_a_drying_deviation_comes_with_its_log_and_the_dryer(auth_client):
    drying = DryingProcessFactory()
    entry = DryingLogEntryFactory(process=drying, day=4, moisture_pct=Decimal("5.8"))
    owner = make_producer_owner(drying.lot.harvest.plot.farm.producer)
    LotNotificationFactory(
        lot=drying.lot,
        recipient=owner,
        kind=NotificationKind.DRYING_OVERDRIED,
        severity=NotificationSeverity.CRITICAL,
        drying_log=entry,
        condition_key=f"{entry.pk}:overdried",
    )

    (row,) = listed(auth_client(owner))

    assert row["drying_log"] == {
        "id": str(entry.pk),
        "day_number": 4,
        "measured_at": timezone.localtime(entry.measured_at).isoformat(),
        "moisture_pct": "5.8",
    }
    assert row["lot"]["drying"]["facility"] == drying.facility.name
    assert row["lot"]["fermentation"] is None


def test_an_unread_overdrying_goes_before_newer_ones(auth_client, owner, process, farm):
    entry = DryingLogEntryFactory(process=DryingProcessFactory(lot=lot_on(farm, LotStatus.DRYING)))
    critical = LotNotificationFactory(
        lot=entry.process.lot,
        recipient=owner,
        kind=NotificationKind.DRYING_OVERDRIED,
        severity=NotificationSeverity.CRITICAL,
        drying_log=entry,
        condition_key="overdried",
    )
    newer = LotNotificationFactory(lot=process.lot, recipient=owner)

    assert ids(auth_client(owner)) == [str(critical.pk), str(newer.pk)]


# Quién los ve.


def test_an_employee_sees_the_lots_of_its_farm_only(auth_client, farm, process):
    other = fermenting_on(FarmFactory(producer=farm.producer))
    employee = make_delegate(farm.producer, [LOTS], farm=farm)
    mine = LotNotificationFactory(lot=process.lot, recipient=employee)
    LotNotificationFactory(lot=other.lot, recipient=employee)

    assert ids(auth_client(employee)) == [str(mine.pk)]
    assert auth_client(employee).get(COUNT_URL).data == {"count": 1}


def test_losing_the_farm_hides_its_lots_and_getting_it_back_shows_them(auth_client, farm, process):
    employee = make_delegate(farm.producer, [LOTS], farm=farm)
    notification = LotNotificationFactory(lot=process.lot, recipient=employee)

    employee.farms.clear()
    assert ids(auth_client(employee)) == []

    employee.farms.add(farm)
    assert ids(auth_client(employee)) == [str(notification.pk)]


def test_without_seeing_lots_their_notifications_stay_hidden(auth_client, farm, process):
    employee = make_delegate(farm.producer, [ACTIVITIES], farm=farm)
    LotNotificationFactory(lot=process.lot, recipient=employee)
    activity = NotificationFactory(recipient=employee, activity__plot=PlotFactory(farm=farm))

    assert ids(auth_client(employee)) == [str(activity.pk)]


def test_seeing_only_lots_is_enough_for_their_notifications(auth_client, farm, process):
    # Antes, sin el permiso de actividades no se veía ningún aviso.
    employee = make_delegate(farm.producer, [LOTS], farm=farm)
    notification = LotNotificationFactory(lot=process.lot, recipient=employee)

    assert ids(auth_client(employee)) == [str(notification.pk)]


def test_the_producer_sees_the_lots_of_every_farm(auth_client, owner, farm, process):
    other = fermenting_on(FarmFactory(producer=farm.producer))
    first = LotNotificationFactory(lot=process.lot, recipient=owner)
    second = LotNotificationFactory(lot=other.lot, recipient=owner)

    assert set(ids(auth_client(owner))) == {str(first.pk), str(second.pk)}


# Sin una consulta por aviso.


def test_listing_twenty_lot_notifications_takes_the_same_queries_as_one(
    auth_client, owner, farm, django_assert_max_num_queries
):
    def one_more():
        turn = FermentationTurnFactory(process=fermenting_on(farm))
        LotNotificationFactory(
            lot=turn.process.lot,
            recipient=owner,
            kind=NotificationKind.FERMENTATION_PH_LOW,
            fermentation_turn=turn,
        )

    one_more()
    client = auth_client(owner)
    with django_assert_max_num_queries(50) as one:
        client.get(LIST_URL)
    for _ in range(19):
        one_more()

    with django_assert_max_num_queries(len(one.captured_queries)):
        response = client.get(LIST_URL)

    assert len(response.data["results"]) == 20
