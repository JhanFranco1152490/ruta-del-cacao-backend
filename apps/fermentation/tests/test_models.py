from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.fermentation.models import FermentationProcessAuditEvent

from .factories import FermentationProcessFactory, FermentationTurnFactory

pytestmark = pytest.mark.django_db


def refused(build):
    """Que la base rechace lo que crea `build`, sin romper la transacción de la prueba."""
    with pytest.raises(IntegrityError), transaction.atomic():
        build()


def test_a_new_fermentation_is_in_progress_and_within_capacity():
    process = FermentationProcessFactory()

    assert (process.ended_at, process.over_capacity, process.end_notes) == (None, False, "")
    assert process.version == 1


def test_the_end_must_come_after_the_start():
    process = FermentationProcessFactory()

    refused(lambda: FermentationProcessFactory(ended_at=process.started_at - timedelta(hours=1)))
    refused(lambda: FermentationProcessFactory(ended_at=process.started_at))


@pytest.mark.parametrize("temperature", ["0.1", "45.0", "80.0"])
def test_the_temperature_is_above_zero_and_up_to_eighty(temperature):
    assert FermentationTurnFactory(temperature_c=Decimal(temperature)).pk


@pytest.mark.parametrize("temperature", ["0.0", "-1.0", "80.1"])
def test_a_temperature_out_of_range_is_refused(temperature):
    refused(lambda: FermentationTurnFactory(temperature_c=Decimal(temperature)))


@pytest.mark.parametrize("ph", ["0.00", "4.85", "14.00"])
def test_the_ph_goes_from_zero_to_fourteen(ph):
    assert FermentationTurnFactory(ph=Decimal(ph)).pk


@pytest.mark.parametrize("ph", ["-0.01", "14.01"])
def test_a_ph_out_of_range_is_refused(ph):
    refused(lambda: FermentationTurnFactory(ph=Decimal(ph)))


def test_two_turns_of_the_same_fermentation_cannot_share_the_minute():
    turn = FermentationTurnFactory()

    refused(lambda: FermentationTurnFactory(process=turn.process, turned_at=turn.turned_at))


def test_two_fermentations_can_turn_at_the_same_minute():
    turn = FermentationTurnFactory()

    assert FermentationTurnFactory(turned_at=turn.turned_at).pk


def test_a_lot_has_at_most_one_fermentation():
    process = FermentationProcessFactory()

    refused(lambda: FermentationProcessFactory(lot=process.lot, facility=process.facility))


def test_the_lot_the_box_and_the_responsible_of_a_fermentation_are_protected():
    process = FermentationProcessFactory()

    for protected in (process.lot, process.facility, process.responsible):
        with pytest.raises(ProtectedError), transaction.atomic():
            protected.delete()


def test_the_author_of_a_turn_is_protected():
    turn = FermentationTurnFactory(recorded_by=FermentationProcessFactory().responsible)

    with pytest.raises(ProtectedError), transaction.atomic():
        turn.recorded_by.delete()


def test_the_history_only_takes_its_own_actions():
    process = FermentationProcessFactory()
    event = FermentationProcessAuditEvent.record(
        process=process, actor=process.responsible, action="started", version=1
    )

    assert event.changes == {}
    with pytest.raises(ValueError):
        FermentationProcessAuditEvent.record(
            process=process, actor=None, action="deleted", version=1
        )
