from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.eggslot import EggLot, EggStage, LossCause
from hatchlot.incubation.picking import (
    Pick,
    PickAlert,
    PickingLog,
    PickLimits,
    apply_pick,
    cumulative_loss,
    picked_by_stage,
)

LOT = "2024-CHK-01"


def lot(green="10000"):
    return EggLot(
        code=LotCode(2024, "CHK", 1),
        take="T-001",
        species="CHK",
        spawned_on=date(2024, 9, 13),
        green_count=Decimal(green),
    )


def pick(day, count, lot_code=LOT, cause=LossCause.PICKED):
    return Pick(day, lot_code, count, "kt", cause)


def test_a_pick_normalises_its_lot_and_keeps_its_picker():
    entry = pick("2024-09-20", 100, lot_code=" 2024 chk 01 ")
    assert entry.lot == "2024-CHK-01"
    assert entry.picked_by == "kt"
    assert entry.day == date(2024, 9, 20)


def test_a_pick_of_nothing_or_by_nobody_is_refused():
    with pytest.raises(ValidationError):
        pick("2024-09-20", 0)
    with pytest.raises(ValidationError):
        Pick("2024-09-20", LOT, 100, "  ")
    with pytest.raises(ValidationError):
        Pick("2024-09-20", LOT, 100, "kt", "fungus")  # type: ignore[arg-type]


def test_the_log_keeps_picks_in_day_order_and_slices_by_lot():
    log = PickingLog([pick("2024-09-21", 50), pick("2024-09-20", 100)])
    log.record(pick("2024-09-22", 20, lot_code="2024-CHK-02"))
    assert len(log) == 3
    assert [entry.count for entry in log.for_lot(LOT)] == [Decimal(100), Decimal(50)]
    assert log.total_for(LOT) == Decimal(150)


def test_the_log_slices_by_window():
    from hatchlot.calendar import DateRange

    log = PickingLog([pick("2024-09-20", 100), pick("2024-10-20", 50)])
    assert len(log.within(DateRange("2024-09-01", "2024-09-30"))) == 1


def test_two_picks_on_one_day_add_up():
    log = PickingLog([pick("2024-09-20", 100), pick("2024-09-20", 40)])
    assert log.picked_on(LOT, "2024-09-20") == Decimal(140)
    assert log.picked_on(LOT, "2024-09-21") == Decimal(0)


def test_the_daily_rate_is_against_what_is_standing():
    log = PickingLog([pick("2024-09-20", 100)])
    assert log.daily_rate(LOT, "2024-09-20", 10000) == Decimal("0.01")
    with pytest.raises(ValidationError):
        log.daily_rate(LOT, "2024-09-20", 0)


def test_the_recent_mean_looks_behind_the_day_and_not_at_it():
    log = PickingLog([pick("2024-09-18", 10), pick("2024-09-19", 10), pick("2024-09-20", 500)])
    assert log.recent_mean(LOT, "2024-09-20", 2) == Decimal(10)
    assert log.recent_mean(LOT, "2024-09-01", 2) == Decimal(0)
    with pytest.raises(ValidationError):
        log.recent_mean(LOT, "2024-09-20", 0)


def test_a_quiet_day_is_normal():
    log = PickingLog([pick("2024-09-20", 10)])
    assert log.classify(LOT, "2024-09-20", 10000) is PickAlert.NORMAL
    assert log.classify(LOT, "2024-09-21", 10000) is PickAlert.NORMAL


def test_a_day_over_the_flat_ceiling_is_a_spike():
    log = PickingLog([pick("2024-09-20", 500)])
    assert log.classify(LOT, "2024-09-20", 10000) is PickAlert.SPIKE


def test_a_day_out_of_line_with_its_own_history_is_elevated():
    log = PickingLog(
        [
            pick("2024-09-16", 10),
            pick("2024-09-17", 10),
            pick("2024-09-18", 10),
            pick("2024-09-19", 10),
            pick("2024-09-20", 60),
        ]
    )
    assert log.classify(LOT, "2024-09-20", 100000) is PickAlert.ELEVATED


def test_a_lot_with_no_history_is_not_elevated_by_its_first_pick():
    log = PickingLog([pick("2024-09-20", 60)])
    assert log.classify(LOT, "2024-09-20", 100000) is PickAlert.NORMAL


def test_the_thresholds_can_be_the_station_s_own():
    log = PickingLog([pick("2024-09-20", 150)])
    tight = PickLimits(daily_ceiling=Decimal("0.001"))
    assert log.classify(LOT, "2024-09-20", 100000) is PickAlert.NORMAL
    assert log.classify(LOT, "2024-09-20", 100000, tight) is PickAlert.SPIKE


def test_impossible_limits_are_refused():
    with pytest.raises(ValidationError):
        PickLimits(daily_ceiling=Decimal(0))
    with pytest.raises(ValidationError):
        PickLimits(spike_multiple=Decimal(0))
    with pytest.raises(ValidationError):
        PickLimits(history_days=1)


def test_only_an_alert_needs_somebody_to_look():
    assert not PickAlert.NORMAL.needs_a_look
    assert PickAlert.ELEVATED.needs_a_look
    assert PickAlert.SPIKE.needs_a_look


def test_applying_a_pick_takes_it_off_the_lot():
    eggs = lot()
    assert apply_pick(eggs, pick("2024-09-20", 500)) == Decimal(9500)
    assert eggs.lost_to(LossCause.PICKED) == Decimal(500)


def test_a_pick_for_another_lot_is_refused():
    with pytest.raises(ValidationError):
        apply_pick(lot(), pick("2024-09-20", 500, lot_code="2024-CHK-02"))


def test_the_cumulative_loss_is_against_the_green_count():
    log = PickingLog([pick("2024-09-20", 100), pick("2024-09-21", 400)])
    assert cumulative_loss(log, LOT, 10000) == Decimal("0.05")
    with pytest.raises(ValidationError):
        cumulative_loss(log, LOT, 0)


def test_picks_split_by_the_stage_the_lot_was_in():
    eggs = lot()
    apply_pick(eggs, pick("2024-09-20", 200))
    eggs.advance(EggStage.EYED)
    apply_pick(eggs, pick("2024-11-01", 50))
    eggs.record_loss("2024-11-02", 25, LossCause.HANDLING)
    split = picked_by_stage(eggs)
    assert split == {EggStage.GREEN: Decimal(200), EggStage.EYED: Decimal(50)}
