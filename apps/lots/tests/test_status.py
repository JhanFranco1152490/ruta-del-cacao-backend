import pytest

from apps.lots.choices import LotStatus, next_status
from apps.lots.exceptions import LotInvalidStatus
from apps.lots.services.status import advance_lot_status
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db

CHAIN = ["generated", "fermenting", "fermented", "drying", "dried"]


def test_the_chain_goes_from_generated_to_dried():
    assert [status.value for status in LotStatus] == CHAIN


def test_each_state_has_one_next_and_the_last_has_none():
    assert [next_status(status) for status in CHAIN[:-1]] == CHAIN[1:]
    assert next_status("dried") is None


def test_advancing_moves_to_the_next_state_and_leaves_the_event():
    lot = LotFactory()
    actor = lot.created_by

    advance_lot_status(lot, LotStatus.GENERATED, LotStatus.FERMENTING, actor=actor)

    lot.refresh_from_db()
    assert (lot.status, lot.version) == ("fermenting", 2)
    event = lot.audit_events.get(action="status_changed")
    assert event.changes == {"status": {"before": "generated", "after": "fermenting"}}
    assert (event.actor, event.version, event.code) == (actor, 2, lot.code)


def test_the_whole_chain_can_be_walked_one_state_at_a_time():
    lot = LotFactory()

    for before, after in zip(CHAIN, CHAIN[1:], strict=False):
        advance_lot_status(lot, before, after, actor=None)

    lot.refresh_from_db()
    assert (lot.status, lot.version) == ("dried", 5)


def test_skipping_a_state_is_refused():
    lot = LotFactory()

    with pytest.raises(LotInvalidStatus) as error:
        advance_lot_status(lot, LotStatus.GENERATED, LotStatus.DRYING, actor=None)

    assert error.value.extra == {"current_status": "generated"}
    lot.refresh_from_db()
    assert (lot.status, lot.version) == ("generated", 1)


def test_going_back_is_refused():
    lot = LotFactory(status=LotStatus.FERMENTED)

    with pytest.raises(LotInvalidStatus):
        advance_lot_status(lot, LotStatus.FERMENTED, LotStatus.FERMENTING, actor=None)


def test_staying_in_the_same_state_is_refused():
    lot = LotFactory()

    with pytest.raises(LotInvalidStatus):
        advance_lot_status(lot, LotStatus.GENERATED, LotStatus.GENERATED, actor=None)


def test_a_lot_that_is_not_in_the_expected_state_is_refused_with_its_current_one():
    lot = LotFactory(status=LotStatus.FERMENTING)

    with pytest.raises(LotInvalidStatus) as error:
        advance_lot_status(lot, LotStatus.GENERATED, LotStatus.FERMENTING, actor=None)

    assert error.value.extra == {"current_status": "fermenting"}


def test_the_last_state_has_nowhere_to_go():
    lot = LotFactory(status=LotStatus.DRIED)

    with pytest.raises(LotInvalidStatus):
        advance_lot_status(lot, LotStatus.DRIED, LotStatus.DRIED, actor=None)
