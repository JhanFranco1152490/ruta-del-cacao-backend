from datetime import timedelta

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.activities.exceptions import ActivityAlreadyDone
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.services.complete import complete_activity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.common.tests.concurrency import run_in_parallel

pytestmark = pytest.mark.django_db(transaction=True)


def attempt(action):
    """El resultado de la acción, o la excepción que lanzó, para comparar lo que pasó en cada
    hilo."""
    try:
        return action()
    except Exception as error:  # noqa: BLE001
        return error


def test_the_same_completion_sent_twice_at_once_is_recorded_once():
    # La cola reenvía mientras el primer envío sigue en curso: el segundo es un reenvío.
    activity = AgriculturalActivityFactory(scheduled_date=today_in_bogota())
    phone_owner = UserFactory(producer=activity.plot.farm.producer)

    results = run_in_parallel(
        lambda _: attempt(
            lambda: complete_activity(
                phone_owner,
                activity.pk,
                {"done_date": today_in_bogota(), "inputs": [], "captured_at": None},
            )
        ),
        [1, 2],
    )

    completed = [result for result in results if isinstance(result, tuple)]
    assert len(completed) == 2
    assert sorted(changed for _, changed in completed) == [False, True]
    assert AgriculturalActivity.objects.get().version == 2
    assert (
        AgriculturalActivityAuditEvent.objects.filter(
            action=AgriculturalActivityAuditEvent.Action.COMPLETED
        ).count()
        == 1
    )


def test_two_phones_with_different_dates_end_with_one_saved_and_one_already_done():
    activity = AgriculturalActivityFactory(scheduled_date=today_in_bogota())
    AgriculturalActivity.objects.filter(pk=activity.pk).update(
        created_at=activity.created_at - timedelta(days=5)
    )
    first = UserFactory(producer=activity.plot.farm.producer)
    second = UserFactory(producer=activity.plot.farm.producer)

    results = run_in_parallel(
        lambda pair: attempt(
            lambda: complete_activity(
                pair[0], activity.pk, {"done_date": pair[1], "inputs": [], "captured_at": None}
            )
        ),
        [(first, today_in_bogota()), (second, today_in_bogota() - timedelta(days=1))],
    )

    completed = [result for result in results if isinstance(result, tuple)]
    rejected = [result for result in results if isinstance(result, ActivityAlreadyDone)]
    assert len(completed) == 1 and len(rejected) == 1
    assert AgriculturalActivity.objects.get().version == 2
