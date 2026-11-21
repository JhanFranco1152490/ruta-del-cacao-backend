from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apps.common.contracts.lot_history import LotHistoryStage
from apps.lots.history_order import order_stages

BOGOTA = ZoneInfo("America/Bogota")
RECORDED = datetime(2026, 3, 1, 8, 0, tzinfo=BOGOTA)


def _at(kind, day, hour, recorded=RECORDED):
    return LotHistoryStage.at(
        kind, datetime(2026, 3, day, hour, 0, tzinfo=BOGOTA), recorded_at=recorded, data=kind
    )


def _on(kind, day, recorded=RECORDED):
    return LotHistoryStage.on(kind, date(2026, 3, day), recorded_at=recorded, data=kind)


def _kinds(stages):
    return [stage.data for stage in order_stages(stages)]


def test_stages_go_from_the_oldest_day_to_the_newest():
    stages = [_on("sale", 20), _at("fermentation", 15, 7), _on("harvest", 14)]

    assert _kinds(stages) == ["harvest", "fermentation", "sale"]


def test_on_the_same_day_the_process_order_wins_over_the_time():
    # El lote se conforma a las 3 p. m. y la cosecha no tiene hora: la cosecha va primero.
    stages = [_at("lot_created", 14, 15), _on("harvest", 14)]

    assert _kinds(stages) == ["harvest", "lot_created"]


def test_an_exit_and_a_sale_with_only_a_date_follow_the_process_order():
    stages = [_on("sale", 20), _on("stock_exit", 20)]

    assert _kinds(stages) == ["stock_exit", "sale"]


def test_two_sales_on_the_same_day_go_by_when_they_were_recorded():
    first = _on("sale", 20, recorded=RECORDED)
    second = _on("sale", 20, recorded=RECORDED + timedelta(hours=2))

    assert order_stages([second, first]) == [first, second]


def test_two_moves_on_the_same_day_go_by_their_time():
    morning = _at("stock_move", 10, 9)
    afternoon = _at("stock_move", 10, 15)

    assert order_stages([afternoon, morning]) == [morning, afternoon]


def test_on_the_same_day_and_kind_a_stage_without_time_goes_first():
    with_time = _at("stock_exit", 12, 9)
    without_time = _on("stock_exit", 12)

    assert order_stages([with_time, without_time]) == [without_time, with_time]


def test_an_earlier_day_wins_even_against_an_earlier_kind():
    stages = [_at("evaluation", 30, 9), _on("stock_entry", 29)]

    assert _kinds(stages) == ["stock_entry", "evaluation"]


def test_no_stages_give_an_empty_history():
    assert order_stages([]) == []
