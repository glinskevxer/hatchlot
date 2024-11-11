from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import DuplicateError, NotFoundError, PolicyError, ValidationError
from hatchlot.feed.feedlot import Analysis, FeedForm, FeedLot
from hatchlot.feed.store import FeedStore, StoreEntry, StoreEvent
from hatchlot.quantities.base import Quantity


def analysis():
    return Analysis(
        protein=Decimal("0.45"),
        fat=Decimal("0.16"),
        fibre=Decimal("0.02"),
        ash=Decimal("0.08"),
        moisture=Decimal("0.09"),
    )


def feed_lot(code="FL-001", pellet="2.0", kilograms="1000", made="2025-01-10"):
    return FeedLot(
        code=code,
        product="starter 45/16",
        form=FeedForm.CRUMBLE,
        pellet_mm=Decimal(pellet),
        analysis=analysis(),
        made_on=date.fromisoformat(made),
        quantity=Quantity(kilograms, "kg"),
    )


def store(*lots):
    shed = FeedStore()
    for lot in lots:
        shed.add(lot)
    return shed


def test_the_store_holds_lots_by_code_and_refuses_a_duplicate():
    shed = store(feed_lot())
    assert len(shed) == 1
    assert shed.get("fl 001").product == "starter 45/16"
    with pytest.raises(DuplicateError):
        shed.add(feed_lot())
    with pytest.raises(NotFoundError):
        shed.get("FL-999")


def test_what_is_on_hand_leaves_out_what_has_expired():
    shed = store(feed_lot(code="FL-001"), feed_lot(code="FL-002", made="2024-01-01"))
    assert shed.on_hand() == Quantity(2000, "kg")
    assert shed.on_hand(as_of="2025-02-01") == Quantity(1000, "kg")


def test_usable_lots_come_back_oldest_first():
    shed = store(
        feed_lot(code="FL-002", made="2025-02-01"),
        feed_lot(code="FL-001", made="2025-01-10"),
    )
    assert [lot.code for lot in shed.usable("2025-03-01")] == ["FL-001", "FL-002"]


def test_an_empty_or_expired_lot_is_not_usable():
    shed = store(
        feed_lot(code="FL-001", kilograms="0"),
        feed_lot(code="FL-002", made="2024-01-01"),
    )
    assert shed.usable("2025-03-01") == ()


def test_lots_can_be_narrowed_to_one_pellet_size():
    shed = store(feed_lot(code="FL-001", pellet="2.0"), feed_lot(code="FL-002", pellet="3.0"))
    assert [lot.code for lot in shed.usable("2025-03-01", pellet_mm="3.0")] == ["FL-002"]
    with pytest.raises(ValidationError):
        shed.usable("2025-03-01", pellet_mm=0)


def test_an_issue_draws_the_oldest_lot_first():
    shed = store(
        feed_lot(code="FL-001", made="2025-01-10", kilograms="100"),
        feed_lot(code="FL-002", made="2025-02-01", kilograms="100"),
    )
    draws = shed.issue("2025-03-01", Quantity(150, "kg"), "kt", "RW-1")
    assert [draw.feed_lot for draw in draws] == ["FL-001", "FL-002"]
    assert draws[0].amount == Quantity(100, "kg")
    assert draws[1].amount == Quantity(50, "kg")
    assert shed.get("FL-001").quantity == Quantity(0, "kg")


def test_an_issue_bigger_than_the_store_is_refused_by_name():
    shed = store(feed_lot(kilograms="100"))
    with pytest.raises(PolicyError) as excinfo:
        shed.issue("2025-03-01", Quantity(500, "kg"), "kt", "RW-1")
    assert excinfo.value.rule == "feed.short"


def test_an_issue_of_nothing_is_refused():
    shed = store(feed_lot())
    with pytest.raises(ValidationError):
        shed.issue("2025-03-01", Quantity(0, "kg"), "kt", "RW-1")


def test_a_receipt_against_a_known_lot_adds_to_it():
    shed = store(feed_lot(kilograms="100"))
    entry = shed.receive(feed_lot(kilograms="50"), "2025-03-01", Quantity(50, "kg"), "kt")
    assert entry.event is StoreEvent.RECEIPT
    assert shed.get("FL-001").quantity == Quantity(150, "kg")


def test_a_receipt_of_a_lot_the_store_has_never_seen_adds_it():
    shed = FeedStore()
    shed.receive(feed_lot(), "2025-03-01", Quantity(1000, "kg"), "kt")
    assert len(shed) == 1
    assert shed.get("FL-001").quantity == Quantity(1000, "kg")


def test_a_disposal_empties_the_lot_and_wants_a_reason():
    shed = store(feed_lot(kilograms="100"))
    entry = shed.dispose("FL-001", "2025-03-01", "kt", "out of date")
    assert entry.event is StoreEvent.DISPOSAL
    assert shed.get("FL-001").quantity == Quantity(0, "kg")
    with pytest.raises(ValidationError):
        shed.dispose("FL-001", "2025-03-02", "kt", "already gone")


def test_a_disposal_with_no_reason_is_refused():
    shed = store(feed_lot())
    with pytest.raises(ValidationError):
        shed.dispose("FL-001", "2025-03-01", "kt", "  ")


def test_the_lots_going_out_of_date_soon():
    shed = store(
        feed_lot(code="FL-001", made="2025-01-10"), feed_lot(code="FL-002", made="2025-06-01")
    )
    soon = shed.expiring_within("2025-07-01", 30)
    assert [lot.code for lot in soon] == ["FL-001"]
    assert shed.expiring_within("2025-07-01", 0) == ()
    with pytest.raises(ValidationError):
        shed.expiring_within("2025-07-01", -1)


def test_what_went_to_one_unit_and_when():
    shed = store(feed_lot(kilograms="1000"))
    shed.issue("2025-03-01", Quantity(100, "kg"), "kt", "RW-1")
    shed.issue("2025-04-01", Quantity(50, "kg"), "kt", "RW-1")
    shed.issue("2025-04-01", Quantity(25, "kg"), "kt", "RW-2")
    assert shed.issued_to("rw 1") == Quantity(150, "kg")
    assert shed.issued_to("RW-1", DateRange("2025-03-01", "2025-03-31")) == Quantity(100, "kg")


def test_the_movements_of_one_feed_lot():
    shed = store(feed_lot(kilograms="1000"))
    shed.issue("2025-03-01", Quantity(100, "kg"), "kt", "RW-1")
    assert len(shed.movements("FL-001")) == 1


def test_a_store_entry_needs_a_person_a_real_event_and_an_amount():
    with pytest.raises(ValidationError):
        StoreEntry(
            day=date(2025, 3, 1),
            feed_lot="FL-001",
            event=StoreEvent.ISSUE,
            amount=Quantity(1, "kg"),
            handled_by=" ",
        )
    with pytest.raises(ValidationError):
        StoreEntry(
            day=date(2025, 3, 1),
            feed_lot="FL-001",
            event="issue",  # type: ignore[arg-type]
            amount=Quantity(1, "kg"),
            handled_by="kt",
        )
    with pytest.raises(ValidationError):
        StoreEntry(
            day=date(2025, 3, 1),
            feed_lot="FL-001",
            event=StoreEvent.ISSUE,
            amount=Quantity(0, "kg"),
            handled_by="kt",
        )


def test_a_receipt_adds_and_everything_else_takes_away():
    assert StoreEvent.RECEIPT.sign == 1
    assert StoreEvent.ISSUE.sign == -1
    assert StoreEvent.DISPOSAL.sign == -1
