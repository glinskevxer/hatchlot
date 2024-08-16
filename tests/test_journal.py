from dataclasses import dataclass
from datetime import date, datetime

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.journal import Journal


@dataclass(frozen=True)
class Entry:
    day: date
    subject: str
    note: str = ""


def journal(*entries):
    log: Journal[Entry] = Journal(
        day_of=lambda entry: entry.day, key_of=lambda entry: entry.subject
    )
    log.extend(entries)
    return log


def entry(day, subject="RW-1", note=""):
    return Entry(date.fromisoformat(day), subject, note)


def test_entries_come_back_in_day_order_whatever_order_they_went_in():
    log = journal(entry("2024-09-03"), entry("2024-09-01"), entry("2024-09-02"))
    assert [item.day.day for item in log] == [1, 2, 3]
    assert len(log) == 3


def test_two_entries_on_one_day_are_ordered_by_their_subject():
    log = journal(entry("2024-09-01", "RW-2"), entry("2024-09-01", "RW-1"))
    assert [item.subject for item in log.all()] == ["RW-1", "RW-2"]


def test_a_journal_slices_by_subject_through_the_sloppy_form():
    log = journal(entry("2024-09-01", "RW-1"), entry("2024-09-02", "RW-2"))
    assert len(log.for_key(" rw 1 ")) == 1
    assert log.keys() == ("RW-1", "RW-2")


def test_a_journal_slices_by_window_and_by_day():
    log = journal(entry("2024-09-01"), entry("2024-10-01"))
    assert len(log.within(DateRange("2024-09-01", "2024-09-30"))) == 1
    assert len(log.on_day("2024-10-01")) == 1
    assert log.on_day("2024-11-01") == ()


def test_the_first_and_last_entry_for_a_subject():
    log = journal(
        entry("2024-09-01", note="first"),
        entry("2024-09-05", note="last"),
        entry("2024-09-03", "RW-2"),
    )
    first = log.first("RW-1")
    latest = log.latest("RW-1")
    assert first is not None and first.note == "first"
    assert latest is not None and latest.note == "last"
    assert log.first("RW-9") is None
    assert log.latest("RW-9") is None


def test_the_span_of_a_journal_and_the_refusal_of_an_empty_one():
    log = journal(entry("2024-09-01"), entry("2024-09-30"))
    assert log.span() == DateRange("2024-09-01", "2024-09-30")
    with pytest.raises(ValidationError):
        journal().span()


def test_a_journal_of_timestamps_sorts_and_slices_on_the_day():
    @dataclass(frozen=True)
    class Stamped:
        taken_at: datetime
        subject: str

    log: Journal[Stamped] = Journal(
        day_of=lambda item: item.taken_at, key_of=lambda item: item.subject
    )
    log.record(Stamped(datetime(2024, 9, 2, 8, 0), "RW-1"))
    log.record(Stamped(datetime(2024, 9, 1, 16, 0), "RW-1"))
    assert [item.taken_at.day for item in log] == [1, 2]
    assert len(log.within(DateRange("2024-09-01", "2024-09-01"))) == 1
