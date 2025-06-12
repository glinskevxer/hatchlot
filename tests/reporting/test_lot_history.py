from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.distribution.release import Release, ReleaseKind, ReleaseRegister
from hatchlot.errors import ValidationError
from hatchlot.feed.feeding import Feeding, FeedingLog, FeedMethod
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry
from hatchlot.rearing.mortality import MortalityCause, MortalityLog, MortalityRecord
from hatchlot.reporting.lot_history import build_history, render_history, timeline

LOT = "2024-CHK-01"


def ledger():
    book = Ledger()
    book.record(LedgerEntry("2025-01-15", LOT, EntryKind.PONDED, 50000, "kt"))
    book.record(LedgerEntry("2025-03-01", LOT, EntryKind.SAMPLE, 200, "kt"))
    return book


def mortality():
    log = MortalityLog()
    log.record(MortalityRecord("2025-02-01", LOT, 500, MortalityCause.DISEASE, "kt"))
    log.record(MortalityRecord("2025-06-01", LOT, 100, MortalityCause.PREDATION, "kt"))
    return log


def feeding():
    log = FeedingLog()
    log.record(Feeding("2025-02-10", LOT, Quantity(100, "kg"), FeedMethod.HAND, "FL-001", "kt"))
    return log


def releases():
    register = ReleaseRegister()
    register.record(
        Release(
            code="RL-001",
            day=date(2025, 5, 1),
            lot=LOT,
            water="LAKE-A",
            request="SR-001",
            fish=Decimal(40000),
            mean_weight=Quantity(20, "g"),
            kind=ReleaseKind.DIRECT,
            released_by="kt",
        )
    )
    return register


def test_the_timeline_merges_every_register_in_day_order():
    events = timeline(LOT, ledger(), mortality(), feeding(), releases())
    kinds = [event.kind for event in events]
    assert kinds[0] == "ponded"
    assert "mortality" in kinds
    assert "feeding" in kinds
    assert "release" in kinds
    assert [event.day for event in events] == sorted(event.day for event in events)


def test_the_timeline_can_be_narrowed_to_a_window():
    events = timeline(
        LOT,
        ledger(),
        mortality(),
        feeding(),
        releases(),
        window=DateRange("2025-02-01", "2025-02-28"),
    )
    assert len(events) == 2


def test_another_lot_gets_none_of_this_lots_events():
    assert timeline("2024-CHK-09", ledger(), mortality(), feeding(), releases()) == ()


def test_an_event_prints_its_count_when_it_has_one():
    events = timeline(LOT, ledger(), mortality(), feeding(), releases())
    ponded = events[0]
    assert "50000" in ponded.line
    fed = next(event for event in events if event.kind == "feeding")
    assert fed.count is None
    assert "FL-001" in fed.line


def test_the_history_gathers_the_numbers_from_every_register():
    history = build_history(LOT, ledger(), mortality(), feeding(), releases())
    assert history.ponded == Decimal(50000)
    assert history.dead == Decimal(600)
    assert history.released == Decimal(40000)
    assert history.fed == Quantity(100, "kg")


def test_the_survival_and_what_is_unaccounted_for():
    history = build_history(LOT, ledger(), mortality(), feeding(), releases())
    assert history.survival == Decimal("0.988")
    assert history.unaccounted == Decimal(9400)


def test_a_lot_with_nothing_on_it_has_no_span_and_no_survival():
    history = build_history(LOT, Ledger(), MortalityLog(), FeedingLog(), ReleaseRegister())
    assert history.span is None
    assert history.survival == Decimal(0)
    assert history.unaccounted == Decimal(0)


def test_the_span_runs_from_the_first_event_to_the_last():
    history = build_history(LOT, ledger(), mortality(), feeding(), releases())
    span = history.span
    assert span is not None
    assert span.start == date(2025, 1, 15)
    assert span.end == date(2025, 6, 1)


def test_the_rendered_history_has_a_heading_a_summary_and_a_table():
    text = render_history(build_history(LOT, ledger(), mortality(), feeding(), releases()))
    assert "Lot history 2024-CHK-01" in text
    assert "survival" in text
    assert "day" in text
    assert "LAKE-A" in text


def test_a_long_history_says_how_much_it_left_out():
    book = Ledger()
    book.record(LedgerEntry("2025-01-15", LOT, EntryKind.PONDED, 50000, "kt"))
    for day in range(1, 20):
        book.record(LedgerEntry(f"2025-03-{day:02d}", LOT, EntryKind.SAMPLE, 10, "kt"))
    history = build_history(LOT, book, MortalityLog(), FeedingLog(), ReleaseRegister())
    text = render_history(history, limit=5)
    assert "15 more events not shown" in text


def test_a_history_that_shows_nothing_is_refused():
    history = build_history(LOT, ledger(), mortality(), feeding(), releases())
    with pytest.raises(ValidationError):
        render_history(history, limit=0)
