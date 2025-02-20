from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.marking import MarkPlan, MarkType, TagCode, summarise_group
from hatchlot.marking.run import MarkingRun, QualityCheck
from hatchlot.marking.summary import expanded_tags, tags_needed, unmarked_remaining

LOT = "2024-CHK-01"


def plan(rate="1.0", lot=LOT):
    return MarkPlan(
        lot=lot,
        marks=(MarkType.ADIPOSE_CLIP, MarkType.CODED_WIRE_TAG),
        tag_code=TagCode("05-12-34"),
        target_rate=Decimal(rate),
    )


def run(code="MR-001", presented="10000", marked="9900", checks=(), day="2025-05-01", rate="1.0"):
    entry = MarkingRun(
        code=code,
        lot=LOT,
        day=date.fromisoformat(day),
        plan=plan(rate),
        presented=Decimal(presented),
        crew="trailer 3",
    )
    entry.start()
    entry.finish(Decimal(marked))
    for check_day, sampled, marked_count, tags in checks:
        entry.check(
            QualityCheck(
                day=date.fromisoformat(check_day),
                sampled=sampled,
                marked=marked_count,
                tags_detected=tags,
            )
        )
    if entry.checks:
        entry.accept()
    return entry


def test_a_group_adds_its_runs_up():
    group = summarise_group(
        plan(),
        [
            run(code="MR-001", presented="10000", marked="9900"),
            run(code="MR-002", presented="5000", marked="4900"),
        ],
    )
    assert group.runs == 2
    assert group.presented == Decimal(15000)
    assert group.marked == Decimal(14800)


def test_a_group_with_no_runs_is_refused():
    with pytest.raises(ValidationError):
        summarise_group(plan(), [])


def test_a_run_from_another_lot_is_refused():
    other = run()
    other.lot = "2024-CHK-02"
    with pytest.raises(ValidationError):
        summarise_group(plan(), [other])


def test_the_rate_comes_off_the_checks_when_there_are_any():
    group = summarise_group(
        plan(),
        [run(checks=[("2025-05-02", 200, 180, 175)])],
    )
    assert group.checked_rate == Decimal("0.9")


def test_the_rate_falls_back_to_the_run_counts_with_no_checks():
    group = summarise_group(plan(), [run(presented="10000", marked="9000")])
    assert group.checked_rate == Decimal("0.9")


def test_the_accepted_runs_are_counted_separately():
    group = summarise_group(
        plan(),
        [
            run(code="MR-001", checks=[("2025-05-02", 200, 200, 195)]),
            run(code="MR-002", marked="5000"),
        ],
    )
    assert group.runs == 2
    assert group.accepted_runs == 1


def test_a_check_taken_on_the_day_gives_no_retention_estimate():
    group = summarise_group(plan(), [run(checks=[("2025-05-01", 200, 200, 190)])])
    assert group.retention is None
    assert "unknown" in group.line()


def test_a_later_check_gives_one():
    group = summarise_group(plan(), [run(checks=[("2025-05-20", 200, 200, 190)])])
    assert group.retention == Decimal("0.95")


def test_a_later_check_that_found_no_marked_fish_reads_as_no_retention():
    group = summarise_group(plan(), [run(checks=[("2025-05-20", 200, 0, 0)])])
    assert group.retention == Decimal(0)


def test_the_retention_window_can_be_moved():
    runs = [run(checks=[("2025-05-03", 200, 200, 190)])]
    assert summarise_group(plan(), runs).retention is None
    assert summarise_group(plan(), runs, retention_after_days=2).retention == Decimal("0.95")


def test_the_effective_rate_takes_the_lost_tags_off():
    group = summarise_group(plan(), [run(checks=[("2025-05-20", 200, 200, 190)])])
    assert group.effective_rate == Decimal("0.95")


def test_the_effective_rate_is_the_checked_rate_when_retention_is_unknown():
    group = summarise_group(plan(), [run(checks=[("2025-05-01", 200, 180, 175)])])
    assert group.effective_rate == group.checked_rate


def test_a_group_that_met_its_target_and_one_that_did_not():
    good = summarise_group(plan(), [run(checks=[("2025-05-02", 200, 200, 195)])])
    poor = summarise_group(plan(), [run(marked="8000", checks=[("2025-05-02", 200, 160, 150)])])
    assert good.meets_target
    assert good.shortfall == Decimal(0)
    assert not poor.meets_target
    assert poor.shortfall == Decimal(2000)


def test_the_tags_a_release_actually_puts_in_the_water():
    group = summarise_group(plan(), [run(checks=[("2025-05-20", 200, 200, 190)])])
    assert expanded_tags(group, 10000) == Decimal(9500)
    with pytest.raises(ValidationError):
        expanded_tags(group, 0)


def test_how_many_tags_to_order():
    assert tags_needed(plan(), 10000) == Decimal(10527)
    assert tags_needed(plan(rate="0.5"), 10000, expected_retention=1) == Decimal(5000)


def test_an_impossible_expected_retention_is_refused():
    with pytest.raises(ValidationError):
        tags_needed(plan(), 10000, expected_retention=0)
    with pytest.raises(ValidationError):
        tags_needed(plan(), 10000, expected_retention="1.5")


def test_the_fish_left_unmarked():
    group = summarise_group(plan(), [run(presented="10000", marked="9000")])
    assert unmarked_remaining(group) == Decimal(1000)


def test_a_fully_marked_group_has_none_left():
    group = summarise_group(plan(), [run(presented="10000", marked="10000")])
    assert unmarked_remaining(group) == Decimal(0)


def test_the_line_reads_like_a_release_report_row():
    group = summarise_group(plan(), [run(checks=[("2025-05-20", 200, 190, 180)])])
    line = group.line()
    assert LOT in line
    assert "retention" in line
