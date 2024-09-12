from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry, adjust_to

LOT = "2024-CHK-01"


def entry(day, kind, count, lot=LOT, reason="", counterparty=""):
    return LedgerEntry(day, lot, kind, count, "kt", reason, counterparty)


def ledger(*entries):
    book = Ledger()
    for item in entries:
        book.record(item)
    return book


def test_the_kinds_know_which_way_they_move_the_count():
    assert EntryKind.PONDED.sign == 1
    assert EntryKind.TRANSFER_IN.sign == 1
    assert EntryKind.MORTALITY.sign == -1
    assert EntryKind.RELEASE.sign == -1
    assert EntryKind.ADJUSTMENT.sign == 0


def test_a_mortality_and_an_adjustment_both_need_a_reason():
    with pytest.raises(ValidationError):
        entry("2025-02-01", EntryKind.MORTALITY, 100)
    with pytest.raises(ValidationError):
        entry("2025-02-01", EntryKind.ADJUSTMENT, 100)
    entry("2025-02-01", EntryKind.MORTALITY, 100, reason="fungus")


def test_an_entry_needs_a_person_a_count_and_a_real_kind():
    with pytest.raises(ValidationError):
        LedgerEntry("2025-02-01", LOT, EntryKind.SAMPLE, 10, "  ")
    with pytest.raises(ValidationError):
        entry("2025-02-01", EntryKind.SAMPLE, 0)
    with pytest.raises(ValidationError):
        LedgerEntry("2025-02-01", LOT, "sample", 10, "kt")  # type: ignore[arg-type]


def test_an_entry_normalises_its_counterparty_when_it_has_one():
    moved = entry("2025-02-01", EntryKind.TRANSFER_OUT, 500, counterparty=" rw 2 ")
    assert moved.counterparty == "RW-2"
    assert entry("2025-02-01", EntryKind.SAMPLE, 10).counterparty == ""


def test_the_effect_of_an_entry_is_signed():
    assert entry("2025-02-01", EntryKind.PONDED, 100).effect == Decimal(100)
    assert entry("2025-02-01", EntryKind.SAMPLE, 100).effect == Decimal(-100)


def test_a_lot_is_rebuilt_from_its_own_history():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 50000),
        entry("2025-02-01", EntryKind.MORTALITY, 500, reason="fungus"),
        entry("2025-03-01", EntryKind.SAMPLE, 100),
        entry("2025-04-01", EntryKind.TRANSFER_IN, 2000),
    )
    balance = book.balance(LOT)
    assert balance.opened == Decimal(50000)
    assert balance.added == Decimal(2000)
    assert balance.removed == Decimal(600)
    assert balance.closing == Decimal(51400)


def test_a_balance_can_be_taken_as_of_a_day():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 50000),
        entry("2025-04-01", EntryKind.TRANSFER_IN, 2000),
    )
    assert book.balance(LOT, as_of="2025-03-01").closing == Decimal(50000)


def test_a_removal_that_would_take_a_lot_below_zero_is_refused():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 100),
        entry("2025-02-01", EntryKind.MORTALITY, 500, reason="pump failure"),
    )
    with pytest.raises(ValidationError):
        book.balance(LOT)


def test_an_adjustment_sets_the_running_count_rather_than_moving_it():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 50000),
        entry("2025-02-01", EntryKind.ADJUSTMENT, 48000, reason="recount after split"),
    )
    balance = book.balance(LOT)
    assert balance.closing == Decimal(48000)
    assert balance.adjusted == Decimal(-2000)


def test_the_loss_share_is_against_everything_that_ever_came_in():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 10000),
        entry("2025-02-01", EntryKind.TRANSFER_IN, 10000),
        entry("2025-03-01", EntryKind.MORTALITY, 2000, reason="ich"),
    )
    assert book.balance(LOT).loss_share == Decimal("0.1")


def test_a_lot_with_nothing_on_it_balances_at_nothing():
    assert Ledger().balance(LOT).closing == Decimal(0)
    assert Ledger().balance(LOT).loss_share == Decimal(0)


def test_the_ledger_slices_by_lot_window_and_kind():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 10000),
        entry("2025-02-01", EntryKind.MORTALITY, 100, reason="fungus"),
        entry("2025-02-01", EntryKind.PONDED, 5000, lot="2024-CHK-02"),
    )
    assert book.lots() == ("2024-CHK-01", "2024-CHK-02")
    assert len(book.for_lot(LOT)) == 2
    assert len(book.within(DateRange("2025-02-01", "2025-02-28"))) == 2
    assert len(book.of_kind(EntryKind.PONDED)) == 2
    assert len(book) == 3


def test_the_mortality_total_for_a_lot():
    book = ledger(
        entry("2025-01-15", EntryKind.PONDED, 10000),
        entry("2025-02-01", EntryKind.MORTALITY, 100, reason="fungus"),
        entry("2025-02-05", EntryKind.MORTALITY, 50, reason="fungus"),
    )
    assert book.mortality(LOT) == Decimal(150)


def test_the_difference_between_a_carried_number_and_the_ledger():
    book = ledger(entry("2025-01-15", EntryKind.PONDED, 10000))
    assert book.check_against(LOT, 10000) == Decimal(0)
    assert book.check_against(LOT, 9500) == Decimal(-500)


def test_an_agreeing_count_writes_no_adjustment():
    book = ledger(entry("2025-01-15", EntryKind.PONDED, 10000))
    assert adjust_to(book, LOT, "2025-06-01", 10000, "kt", "annual count") is None
    assert len(book) == 1


def test_a_disagreeing_count_writes_one_and_the_ledger_then_agrees():
    book = ledger(entry("2025-01-15", EntryKind.PONDED, 10000))
    written = adjust_to(book, LOT, "2025-06-01", 9500, "kt", "annual count")
    assert written is not None
    assert written.kind is EntryKind.ADJUSTMENT
    assert book.balance(LOT).closing == Decimal(9500)
    assert book.check_against(LOT, 9500) == Decimal(0)


def test_an_adjustment_without_a_reason_is_still_refused_through_the_helper():
    book = ledger(entry("2025-01-15", EntryKind.PONDED, 10000))
    with pytest.raises(ValidationError):
        adjust_to(book, LOT, "2025-06-01", 9500, "kt", "  ")
