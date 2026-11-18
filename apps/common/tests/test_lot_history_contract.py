from datetime import UTC, date, datetime

import pytest
from rest_framework import serializers

from apps.common.contracts import lot_history
from apps.common.contracts.lot_history import (
    LOT_HISTORY_SOURCES,
    STAGE_KINDS,
    LotHistoryStage,
    lot_history_source,
    register_lot_history_source,
    register_stage_serializer,
    stage_days,
    stage_serializers,
)
from apps.common.contracts.sources import SourceRegistry

RECORDED_AT = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


class _Data(serializers.Serializer):
    note = serializers.CharField()


@pytest.fixture
def empty_registries(monkeypatch):
    monkeypatch.setattr(
        lot_history, "_sources", SourceRegistry("de la historia del lote", LOT_HISTORY_SOURCES)
    )
    monkeypatch.setattr(lot_history, "_serializers", {})


def test_the_stage_kinds_follow_the_process_without_repeating():
    assert STAGE_KINDS == (
        "harvest",
        "lot_created",
        "fermentation",
        "drying",
        "evaluation",
        "classification",
        "discard",
        "stock_entry",
        "stock_move",
        "stock_exit",
        "sale",
    )
    assert len(set(STAGE_KINDS)) == len(STAGE_KINDS)


def test_a_stage_with_a_time_falls_on_its_local_day():
    # Las 2:00 a. m. en UTC del 15 son las 9:00 p. m. del 14 en Bogotá.
    at = datetime(2026, 3, 15, 2, 0, tzinfo=UTC)

    stage = LotHistoryStage.at("fermentation", at, recorded_at=RECORDED_AT, data={})

    assert stage.occurred_on == date(2026, 3, 14)
    assert stage.occurred_at == at


def test_a_stage_with_only_a_date_has_no_time():
    stage = LotHistoryStage.on("sale", date(2026, 4, 20), recorded_at=RECORDED_AT, data={})

    assert stage.occurred_on == date(2026, 4, 20)
    assert stage.occurred_at is None


def test_a_stage_of_an_unknown_kind_cannot_be_built():
    with pytest.raises(ValueError):
        LotHistoryStage.on("activity", date(2026, 4, 20), recorded_at=RECORDED_AT, data={})


def test_a_registered_source_is_returned_by_its_name(empty_registries):
    def fermentation_history(lot):
        return []

    register_lot_history_source("fermentation_history", fermentation_history)

    assert lot_history_source("fermentation_history") is fermentation_history


def test_asking_for_a_history_source_nobody_registered_fails_loudly(empty_registries):
    with pytest.raises(RuntimeError):
        lot_history_source("sales_history")


def test_a_history_source_outside_the_known_names_cannot_be_registered(empty_registries):
    with pytest.raises(ValueError):
        register_lot_history_source("activities_history", lambda lot: [])


def test_each_kind_builds_a_new_serializer_for_its_data(empty_registries):
    register_stage_serializer("sale", _Data)

    built = stage_serializers()

    assert set(built) == {"sale"}
    assert isinstance(built["sale"], _Data)
    assert stage_serializers()["sale"] is not built["sale"]


def test_a_serializer_for_an_unknown_kind_cannot_be_registered(empty_registries):
    with pytest.raises(ValueError):
        register_stage_serializer("activity", _Data)


def test_the_days_of_a_stage_count_local_days_from_start_to_end():
    started = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
    # Las 3:00 UTC del 21 todavía son el 20 en Bogotá.
    ended = datetime(2026, 3, 21, 3, 0, tzinfo=UTC)

    assert stage_days(started, ended, today=date(2026, 4, 1)) == 5


def test_a_running_stage_counts_its_days_until_today():
    started = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)

    assert stage_days(started, None, today=date(2026, 3, 18)) == 3
    assert stage_days(started, None, today=date(2026, 3, 15)) == 0
