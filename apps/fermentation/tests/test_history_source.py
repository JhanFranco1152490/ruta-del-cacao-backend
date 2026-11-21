from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.common.contracts.lot_history import (
    LotHistoryStage,
    lot_history_source,
    stage_serializers,
)
from apps.fermentation.history import (
    FermentationData,
    FermentationTurnData,
    turn_summary,
)
from apps.fermentation.tests.factories import (
    FermentationProcessFactory,
    FermentationTurnFactory,
)
from apps.lots.tests.factories import LotFactory

BOGOTA = ZoneInfo("America/Bogota")
STARTED = datetime(2026, 3, 15, 7, 0, tzinfo=BOGOTA)


def _turn(hours, temperature, ph):
    return FermentationTurnData(
        turned_at=STARTED + timedelta(hours=hours),
        temperature_c=Decimal(temperature),
        ph=Decimal(ph),
    )


def test_the_summary_of_no_turns_has_no_extremes():
    assert turn_summary(()) == {
        "turn_count": 0,
        "temperature_min_c": None,
        "temperature_max_c": None,
        "ph_min": None,
        "ph_max": None,
        "last_turn_at": None,
    }


def test_the_summary_takes_the_extremes_and_the_last_turn():
    turns = (_turn(24, "42.0", "4.90"), _turn(48, "47.5", "4.20"), _turn(72, "38.0", "5.10"))

    assert turn_summary(turns) == {
        "turn_count": 3,
        "temperature_min_c": Decimal("38.0"),
        "temperature_max_c": Decimal("47.5"),
        "ph_min": Decimal("4.20"),
        "ph_max": Decimal("5.10"),
        "last_turn_at": STARTED + timedelta(hours=72),
    }


@pytest.mark.django_db
def test_a_lot_without_fermentation_has_no_stage():
    lot = LotFactory()

    assert lot_history_source("fermentation_history")(lot.pk) == []


@pytest.mark.django_db
def test_a_running_fermentation_without_turns_has_no_end():
    process = FermentationProcessFactory(
        started_at=STARTED,
        facility__name="Cajón 1",
        responsible__first_name="Pedro",
        responsible__last_name="Gómez",
    )

    [stage] = lot_history_source("fermentation_history")(process.lot_id)

    assert isinstance(stage, LotHistoryStage)
    assert stage.kind == "fermentation"
    assert stage.occurred_at == STARTED
    assert stage.recorded_at == process.created_at
    data = stage.data
    assert isinstance(data, FermentationData)
    assert data.ended_at is None
    assert data.facility == "Cajón 1"
    assert data.responsible == "Pedro Gómez"
    assert data.turn_count == 0
    assert data.turns == ()


@pytest.mark.django_db
def test_a_finished_fermentation_brings_its_turns_in_order_and_its_days():
    process = FermentationProcessFactory(
        started_at=STARTED, ended_at=STARTED + timedelta(days=6, minutes=30)
    )
    late = FermentationTurnFactory(
        process=process,
        turned_at=STARTED + timedelta(hours=48),
        temperature_c=Decimal("47.5"),
        ph=Decimal("4.20"),
    )
    early = FermentationTurnFactory(
        process=process,
        turned_at=STARTED + timedelta(hours=24),
        temperature_c=Decimal("42.0"),
        ph=Decimal("4.90"),
    )
    FermentationTurnFactory()

    [stage] = lot_history_source("fermentation_history")(process.lot_id)

    data = stage.data
    assert data.ended_at == process.ended_at
    assert data.days == 6
    assert [turn.turned_at for turn in data.turns] == [early.turned_at, late.turned_at]
    assert (data.turn_count, data.temperature_max_c, data.ph_min) == (
        2,
        Decimal("47.5"),
        Decimal("4.20"),
    )
    assert data.last_turn_at == late.turned_at


@pytest.mark.django_db
def test_many_turns_take_the_same_queries(django_assert_num_queries):
    process = FermentationProcessFactory(started_at=STARTED)
    for hours in range(1, 21):
        FermentationTurnFactory(process=process, turned_at=STARTED + timedelta(hours=hours))

    with django_assert_num_queries(2):
        [stage] = lot_history_source("fermentation_history")(process.lot_id)

    assert stage.data.turn_count == 20


@pytest.mark.django_db
def test_the_stage_is_serialized_with_one_decimal_of_temperature_and_two_of_ph():
    process = FermentationProcessFactory(started_at=STARTED)
    FermentationTurnFactory(
        process=process,
        turned_at=STARTED + timedelta(hours=24),
        temperature_c=Decimal("42"),
        ph=Decimal("4.9"),
    )
    [stage] = lot_history_source("fermentation_history")(process.lot_id)

    data = stage_serializers()["fermentation"].to_representation(stage.data)

    assert data["temperature_min_c"] == "42.0"
    assert data["ph_max"] == "4.90"
    assert data["turns"][0]["temperature_c"] == "42.0"
    assert data["turns"][0]["ph"] == "4.90"
    assert data["facility"] == process.facility.name
