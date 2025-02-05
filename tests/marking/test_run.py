from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, StateError, ValidationError
from hatchlot.marking.mark import MarkPlan, MarkType, TagCode
from hatchlot.marking.run import (
    MarkingRun,
    QualityCheck,
    RunState,
    require_accepted,
)

LOT = "2024-CHK-01"


def plan(rate="1.0"):
    return MarkPlan(
        lot=LOT,
        marks=(MarkType.ADIPOSE_CLIP, MarkType.CODED_WIRE_TAG),
        tag_code=TagCode("05-12-34"),
        target_rate=Decimal(rate),
    )


def run(presented="10000", rate="1.0"):
    return MarkingRun(
        code="MR-001",
        lot=LOT,
        day=date(2025, 5, 1),
        plan=plan(rate),
        presented=Decimal(presented),
        crew="trailer 3",
    )


def check(day="2025-05-05", sampled=200, marked=198, tags=190):
    return QualityCheck(
        day=date.fromisoformat(day), sampled=sampled, marked=marked, tags_detected=tags
    )


def test_a_run_normalises_its_codes_and_needs_a_crew():
    entry = run()
    assert entry.code == "MR-001"
    assert entry.state is RunState.PLANNED
    with pytest.raises(ValidationError):
        MarkingRun(
            code="MR-1",
            lot=LOT,
            day=date(2025, 5, 1),
            plan=plan(),
            presented=Decimal(100),
            crew=" ",
        )


def test_a_run_whose_plan_is_for_another_lot_is_refused():
    other = MarkPlan(lot="2024-CHK-02", marks=(MarkType.ADIPOSE_CLIP,))
    with pytest.raises(ValidationError):
        MarkingRun(
            code="MR-1",
            lot=LOT,
            day=date(2025, 5, 1),
            plan=other,
            presented=Decimal(100),
            crew="trailer 3",
        )


def test_a_run_of_no_fish_is_refused():
    with pytest.raises(ValidationError):
        run(presented="0")


def test_a_run_goes_planned_then_running_then_checked():
    entry = run()
    entry.start()
    assert entry.state is RunState.RUNNING
    entry.finish(9800, 100)
    assert entry.state.value == "checked"
    assert entry.marked == Decimal(9800)


def test_a_run_cannot_be_started_twice_or_finished_before_it_starts():
    entry = run()
    with pytest.raises(StateError):
        entry.finish(100)
    entry.start()
    with pytest.raises(StateError):
        entry.start()


def test_more_fish_out_than_went_in_is_refused():
    entry = run(presented="1000")
    entry.start()
    with pytest.raises(ValidationError):
        entry.finish(900, 200)
    with pytest.raises(ValidationError):
        entry.finish(-1)


def test_a_check_cannot_precede_the_run_or_come_before_it_ran():
    entry = run()
    with pytest.raises(StateError):
        entry.check(check())
    entry.start()
    with pytest.raises(ValidationError):
        entry.check(check(day="2025-04-01"))


def test_a_quality_check_reports_three_different_shares():
    sample = check(sampled=200, marked=198, tags=190)
    assert sample.mark_share == Decimal("0.99")
    assert sample.tag_share == Decimal("0.95")
    assert sample.retention.quantize(Decimal("0.0001")) == Decimal("0.9596")


def test_a_check_with_no_marked_fish_has_no_retention():
    assert check(sampled=200, marked=0, tags=0).retention == Decimal(0)


def test_an_impossible_check_is_refused():
    with pytest.raises(ValidationError):
        QualityCheck(day=date(2025, 5, 5), sampled=0, marked=0)
    with pytest.raises(ValidationError):
        QualityCheck(day=date(2025, 5, 5), sampled=100, marked=200)
    with pytest.raises(ValidationError):
        QualityCheck(day=date(2025, 5, 5), sampled=100, marked=50, tags_detected=200)


def test_a_run_that_hit_its_rate_is_accepted():
    entry = run()
    entry.start()
    entry.finish(9900)
    entry.check(check(sampled=200, marked=199, tags=195))
    assert entry.accept() is RunState.ACCEPTED
    assert entry.state.is_finished


def test_a_run_that_missed_its_rate_is_rejected():
    entry = run()
    entry.start()
    entry.finish(8000)
    entry.check(check(sampled=200, marked=160, tags=150))
    assert entry.accept() is RunState.REJECTED


def test_a_run_cannot_be_accepted_without_a_check():
    entry = run()
    entry.start()
    entry.finish(9900)
    with pytest.raises(StateError):
        entry.accept()


def test_a_run_is_accepted_once():
    entry = run()
    entry.start()
    entry.finish(9900)
    entry.check(check())
    entry.accept()
    with pytest.raises(StateError):
        entry.accept()


def test_a_negative_tolerance_is_refused():
    entry = run()
    entry.start()
    entry.finish(9900)
    entry.check(check())
    with pytest.raises(ValidationError):
        entry.accept(tolerance="-0.1")


def test_several_checks_are_weighted_by_how_many_fish_they_looked_at():
    entry = run()
    entry.start()
    entry.finish(9000)
    entry.check(check(sampled=100, marked=100, tags=95))
    entry.check(check(sampled=300, marked=240, tags=230))
    assert entry.checked_rate() == Decimal("0.85")


def test_the_rate_off_the_run_itself_before_anybody_checks():
    entry = run(presented="10000")
    entry.start()
    entry.finish(9000)
    assert entry.applied_rate == Decimal("0.9")
    assert run().applied_rate == Decimal(0)


def test_the_shortfall_is_what_still_needs_marking():
    entry = run(presented="10000")
    entry.start()
    entry.finish(9000)
    entry.check(check(sampled=200, marked=180, tags=170))
    assert entry.shortfall == Decimal(1000)


def test_a_run_that_met_the_plan_has_no_shortfall():
    entry = run(presented="10000", rate="0.5")
    entry.start()
    entry.finish(6000)
    entry.check(check(sampled=200, marked=120, tags=115))
    assert entry.shortfall == Decimal(0)


def test_the_shortfall_falls_back_to_the_run_count_with_no_checks():
    entry = run(presented="10000")
    entry.start()
    entry.finish(9000)
    assert entry.shortfall == Decimal(1000)


def test_a_check_has_to_land_inside_the_window_to_count():
    entry = run()
    entry.start()
    entry.finish(9900)
    entry.check(check(day="2025-06-01"))
    assert entry.check_window() == date(2025, 5, 15)
    assert not entry.is_checked_in_time()
    entry.check(check(day="2025-05-05"))
    assert entry.is_checked_in_time()
    with pytest.raises(ValidationError):
        entry.check_window(days=0)


def test_a_group_off_an_unaccepted_run_cannot_be_released():
    entry = run()
    with pytest.raises(PolicyError) as excinfo:
        require_accepted(entry)
    assert excinfo.value.rule == "marking.unaccepted"
    entry.start()
    entry.finish(9900)
    entry.check(check())
    entry.accept()
    require_accepted(entry)
