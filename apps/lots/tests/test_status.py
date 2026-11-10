import pytest

from apps.lots.choices import LotStatus, allowed_next
from apps.lots.exceptions import LotInvalidStatus
from apps.lots.services.status import advance_lot_status
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db

CHAIN = [
    "generated",
    "fermenting",
    "fermented",
    "drying",
    "dried",
    "evaluated",
    "classified",
    "in_warehouse",
]

EXPECTED_TRANSITIONS = {
    "generated": {"fermenting"},
    "fermenting": {"fermented"},
    "fermented": {"drying"},
    "drying": {"dried"},
    "dried": {"evaluated"},
    "evaluated": {"classified", "discarded"},
    "classified": {"in_warehouse"},
    "in_warehouse": set(),
    "discarded": set(),
}


def test_the_states_go_in_the_order_of_the_process():
    assert [status.value for status in LotStatus] == [*CHAIN, "discarded"]


def test_each_state_leads_only_to_its_next_ones():
    assert {status: set(allowed_next(status)) for status in LotStatus} == EXPECTED_TRANSITIONS


@pytest.mark.parametrize("before", [status.value for status in LotStatus])
@pytest.mark.parametrize("after", [status.value for status in LotStatus])
def test_every_pair_outside_the_transitions_is_refused(before, after):
    lot = LotFactory(status=before)

    if after in EXPECTED_TRANSITIONS[before]:
        advance_lot_status(lot, before, after, actor=None)
        lot.refresh_from_db()
        assert lot.status == after
    else:
        with pytest.raises(LotInvalidStatus):
            advance_lot_status(lot, before, after, actor=None)
        lot.refresh_from_db()
        assert (lot.status, lot.version) == (before, 1)


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
    assert (lot.status, lot.version) == ("in_warehouse", 8)


def test_an_evaluated_lot_can_be_discarded_instead_of_classified():
    lot = LotFactory(status=LotStatus.EVALUATED)

    advance_lot_status(lot, LotStatus.EVALUATED, LotStatus.DISCARDED, actor=lot.created_by)

    lot.refresh_from_db()
    assert lot.status == "discarded"
    event = lot.audit_events.get(action="status_changed")
    assert event.changes == {"status": {"before": "evaluated", "after": "discarded"}}


def test_a_classified_lot_cannot_be_discarded():
    lot = LotFactory(status=LotStatus.CLASSIFIED)

    with pytest.raises(LotInvalidStatus) as error:
        advance_lot_status(lot, LotStatus.CLASSIFIED, LotStatus.DISCARDED, actor=None)

    assert error.value.extra == {"current_status": "classified"}


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


@pytest.mark.parametrize("final", [LotStatus.IN_WAREHOUSE, LotStatus.DISCARDED])
def test_the_final_states_have_nowhere_to_go(final):
    lot = LotFactory(status=final)

    for target in LotStatus:
        with pytest.raises(LotInvalidStatus):
            advance_lot_status(lot, final, target, actor=None)


def test_the_lot_advances_itself_with_the_same_rules():
    # Fermentación y secado no importan esta app: cambian el estado por el método del modelo.
    lot = LotFactory()

    lot.advance_status(LotStatus.GENERATED, LotStatus.FERMENTING, actor=lot.created_by)

    lot.refresh_from_db()
    assert (lot.status, lot.version) == ("fermenting", 2)
    assert lot.audit_events.filter(action="status_changed").count() == 1
    with pytest.raises(LotInvalidStatus):
        lot.advance_status(LotStatus.FERMENTING, LotStatus.DRYING, actor=None)
