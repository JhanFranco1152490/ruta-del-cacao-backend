from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.common.contracts.lot_history import (
    LotHistoryStage,
    lot_history_source,
    stage_serializers,
)
from apps.drying.history import DryingData, DryingLogData, log_summary
from apps.drying.tests.factories import DryingLogEntryFactory, DryingProcessFactory
from apps.lots.tests.factories import LotFactory

BOGOTA = ZoneInfo("America/Bogota")
STARTED = datetime(2026, 3, 21, 8, 0, tzinfo=BOGOTA)


def _log(day, moisture, sun):
    return DryingLogData(
        day_number=day,
        log_date=date(2026, 3, 20 + day),
        moisture_pct=Decimal(moisture),
        sun_hours=Decimal(sun),
        weather="sunny",
    )


def test_the_summary_of_no_logs_has_no_last_moisture_and_no_sun():
    assert log_summary((), stored_sun_hours=None) == {
        "log_count": 0,
        "last_moisture_pct": None,
        "total_sun_hours": Decimal("0.0"),
    }


def test_a_running_drying_adds_the_sun_hours_of_its_logs():
    logs = (_log(1, "50.0", "5.5"), _log(2, "38.0", "6.0"))

    assert log_summary(logs, stored_sun_hours=None) == {
        "log_count": 2,
        "last_moisture_pct": Decimal("38.0"),
        "total_sun_hours": Decimal("11.5"),
    }


def test_a_finished_drying_keeps_the_sun_hours_it_saved():
    logs = (_log(1, "50.0", "5.5"),)

    summary = log_summary(logs, stored_sun_hours=Decimal("46.0"))

    assert summary["total_sun_hours"] == Decimal("46.0")


@pytest.mark.django_db
def test_a_lot_without_drying_has_no_stage():
    assert lot_history_source("drying_history")(LotFactory().pk) == []


@pytest.mark.django_db
def test_a_running_drying_without_logs_has_no_result():
    process = DryingProcessFactory(
        started_at=STARTED,
        entry_moisture_pct=Decimal("55.0"),
        facility__name="Marquesina 2",
        responsible__first_name="Pedro",
        responsible__last_name="Gómez",
    )

    [stage] = lot_history_source("drying_history")(process.lot_id)

    assert isinstance(stage, LotHistoryStage)
    assert stage.kind == "drying"
    assert stage.occurred_at == STARTED
    assert stage.recorded_at == process.created_at
    data = stage.data
    assert isinstance(data, DryingData)
    assert (data.facility, data.responsible) == ("Marquesina 2", "Pedro Gómez")
    assert data.entry_moisture_pct == Decimal("55.0")
    assert (data.ended_at, data.final_moisture_pct, data.dry_weight_kg, data.yield_pct) == (
        None,
        None,
        None,
        None,
    )
    assert (data.log_count, data.last_moisture_pct, data.logs) == (0, None, ())


@pytest.mark.django_db
def test_a_finished_drying_brings_its_logs_in_order_and_its_result():
    process = DryingProcessFactory(
        started_at=STARTED,
        ended_at=STARTED + timedelta(days=8),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal("45.0"),
        yield_pct=Decimal("37.5"),
        total_sun_hours=Decimal("46.0"),
    )
    DryingLogEntryFactory(process=process, day=2, moisture_pct=Decimal("30.0"))
    DryingLogEntryFactory(process=process, day=1, moisture_pct=Decimal("48.0"))
    DryingLogEntryFactory()

    [stage] = lot_history_source("drying_history")(process.lot_id)

    data = stage.data
    assert data.days == 8
    assert [log.day_number for log in data.logs] == [1, 2]
    assert data.last_moisture_pct == Decimal("30.0")
    assert (data.final_moisture_pct, data.dry_weight_kg, data.yield_pct) == (
        Decimal("7.0"),
        Decimal("45.0"),
        Decimal("37.5"),
    )
    assert data.total_sun_hours == Decimal("46.0")


@pytest.mark.django_db
def test_many_logs_take_the_same_queries(django_assert_num_queries):
    process = DryingProcessFactory(started_at=STARTED)
    for day in range(1, 16):
        DryingLogEntryFactory(process=process, day=day)

    with django_assert_num_queries(2):
        [stage] = lot_history_source("drying_history")(process.lot_id)

    assert stage.data.log_count == 15


@pytest.mark.django_db
def test_the_stage_is_serialized_with_its_logs():
    process = DryingProcessFactory(started_at=STARTED)
    DryingLogEntryFactory(
        process=process, day=1, moisture_pct=Decimal("48"), sun_hours=Decimal("5")
    )
    [stage] = lot_history_source("drying_history")(process.lot_id)

    data = stage_serializers()["drying"].to_representation(stage.data)

    assert data["last_moisture_pct"] == "48.0"
    assert data["total_sun_hours"] == "5.0"
    assert data["yield_pct"] is None
    assert data["logs"] == [
        {
            "day_number": 1,
            "log_date": "2026-03-21",
            "moisture_pct": "48.0",
            "sun_hours": "5.0",
            "weather": "sunny",
        }
    ]
