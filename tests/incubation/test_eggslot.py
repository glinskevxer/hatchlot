from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import StateError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.eggslot import (
    EggLot,
    EggStage,
    LossCause,
    combined_survival,
    total_eggs,
)


def lot(code=1, green="10000"):
    return EggLot(
        code=LotCode(2024, "CHK", code),
        take="T-001",
        species="chk",
        spawned_on=date(2024, 9, 13),
        green_count=green,
    )


def test_a_lot_starts_green_with_everything_on_it():
    entry = lot()
    assert entry.stage is EggStage.GREEN
    assert entry.count == Decimal(10000)
    assert entry.survival == Decimal(1)
    assert entry.lost == Decimal(0)


def test_a_lot_needs_a_real_lot_code_and_a_real_count():
    with pytest.raises(ValidationError):
        EggLot(
            code="2024-CHK-01",  # type: ignore[arg-type]
            take="T-1",
            species="CHK",
            spawned_on=date(2024, 9, 13),
            green_count=Decimal(100),
        )
    with pytest.raises(ValidationError):
        lot(green="0")


def test_the_stages_run_in_the_order_incubation_goes_through_them():
    order = [stage.order for stage in (EggStage.GREEN, EggStage.EYED, EggStage.HATCHED)]
    assert order == sorted(order)
    assert EggStage.PONDED.is_closed
    assert not EggStage.EYED.is_closed


def test_a_loss_comes_straight_off_the_count():
    entry = lot()
    entry.record_loss("2024-09-20", 500, LossCause.UNFERTILISED)
    assert entry.count == Decimal(9500)
    assert entry.survival == Decimal("0.95")
    assert entry.lost_to(LossCause.UNFERTILISED) == Decimal(500)


def test_a_loss_bigger_than_the_lot_is_refused():
    entry = lot(green="100")
    with pytest.raises(ValidationError):
        entry.record_loss("2024-09-20", 200, LossCause.FUNGUS)


def test_a_loss_of_nothing_is_not_a_loss():
    with pytest.raises(ValidationError):
        lot().record_loss("2024-09-20", 0, LossCause.FUNGUS)


def test_a_loss_cause_that_is_not_one_is_refused():
    with pytest.raises(ValidationError):
        lot().record_loss("2024-09-20", 100, "fungus")


def test_losses_cannot_be_written_out_of_order():
    entry = lot()
    entry.record_loss("2024-09-20", 100, LossCause.FUNGUS)
    with pytest.raises(ValidationError):
        entry.record_loss("2024-09-14", 100, LossCause.FUNGUS)


def test_a_loss_is_filed_against_the_stage_the_lot_was_in():
    entry = lot()
    entry.record_loss("2024-09-20", 100, LossCause.UNFERTILISED)
    entry.advance(EggStage.EYED)
    entry.record_loss("2024-11-01", 50, LossCause.SHOCK)
    assert entry.lost_at(EggStage.GREEN) == Decimal(100)
    assert entry.lost_at(EggStage.EYED) == Decimal(50)


def test_a_lot_moves_forward_only():
    entry = lot()
    entry.advance(EggStage.EYED)
    with pytest.raises(StateError):
        entry.advance(EggStage.GREEN)
    with pytest.raises(StateError):
        entry.advance(EggStage.EYED)


def test_a_stage_that_is_not_a_stage_is_refused():
    with pytest.raises(ValidationError):
        lot().advance("eyed")


def test_a_ponded_lot_is_finished_with():
    entry = lot()
    entry.advance(EggStage.EYED)
    entry.advance(EggStage.PONDED)
    with pytest.raises(StateError):
        entry.record_loss("2024-12-01", 10, LossCause.HANDLING)
    with pytest.raises(StateError):
        entry.advance(EggStage.HATCHED)
    with pytest.raises(StateError):
        entry.move_to("RW-1")


def test_a_lot_can_be_written_off_from_anywhere_with_a_reason():
    entry = lot()
    entry.advance(EggStage.EYED)
    entry.write_off("water off overnight")
    assert entry.stage is EggStage.WRITTEN_OFF
    assert entry.note == "water off overnight"
    with pytest.raises(ValidationError):
        lot(code=2).write_off("  ")


def test_a_lot_records_where_it_is_sitting():
    entry = lot()
    assert entry.unit == ""
    assert entry.move_to(" jar 12 ") == "JAR-12"


def test_the_loss_rate_is_against_the_green_count_not_what_is_left():
    entry = lot(green="10000")
    entry.record_loss("2024-09-20", 1000, LossCause.UNFERTILISED)
    entry.record_loss("2024-09-25", 500, LossCause.FUNGUS)
    assert entry.loss_rate(LossCause.UNFERTILISED) == Decimal("0.1")
    assert entry.loss_rate(LossCause.FUNGUS) == Decimal("0.05")


def test_days_incubating_and_the_refusal_of_a_day_before_the_take():
    entry = lot()
    assert entry.days_incubating("2024-10-13") == 30
    with pytest.raises(ValidationError):
        entry.days_incubating("2024-09-01")


def test_totals_across_a_set_of_lots():
    first = lot(code=1, green="10000")
    second = lot(code=2, green="5000")
    first.record_loss("2024-09-20", 1000, LossCause.UNFERTILISED)
    assert total_eggs([first, second]) == Decimal(14000)
    assert combined_survival([first, second]).quantize(Decimal("0.0001")) == Decimal("0.9333")


def test_combining_no_lots_is_refused():
    with pytest.raises(ValidationError):
        combined_survival([])
