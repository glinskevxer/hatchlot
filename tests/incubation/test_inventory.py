from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.eggslot import EggLot, EggStage, LossCause
from hatchlot.incubation.inventory import (
    occupancy,
    reconcile_room,
    record_total,
    room_total,
)
from hatchlot.incubation.vessel import Vessel, VesselKind, VesselRegister
from hatchlot.quantities.base import Quantity


def lot(sequence=1, green="10000", stage=EggStage.EYED):
    return EggLot(
        code=LotCode(2024, "CHK", sequence),
        take="T-001",
        species="CHK",
        spawned_on=date(2024, 9, 13),
        green_count=Decimal(green),
        stage=stage,
    )


def room(*loads):
    register = VesselRegister()
    for code, lot_code, eggs in loads:
        if code not in register:
            register.add(
                Vessel(
                    code=code,
                    kind=VesselKind.TRAY,
                    flow=Quantity(20, "Lpm"),
                    capacity_eggs=Decimal(12000),
                )
            )
        if lot_code:
            register.get(code).load(lot_code, eggs)
    return register


def test_a_room_that_agrees_with_its_records_is_clean():
    result = reconcile_room([lot()], room(("TR-1", "2024-CHK-01", 10000)))
    assert result.is_clean
    assert result.checked == 1
    assert result.worst is None


def test_a_small_difference_is_inside_the_tolerance():
    result = reconcile_room([lot()], room(("TR-1", "2024-CHK-01", 9950)))
    assert result.is_clean


def test_a_real_difference_is_reported_with_its_direction():
    result = reconcile_room([lot()], room(("TR-1", "2024-CHK-01", 9000)))
    assert not result.is_clean
    assert len(result.discrepancies) == 1
    entry = result.discrepancies[0]
    assert entry.difference == Decimal(-1000)
    assert entry.direction == "short"
    assert entry.percent == Decimal(-10)


def test_an_over_count_reads_the_other_way():
    result = reconcile_room([lot()], room(("TR-1", "2024-CHK-01", 11000)))
    assert result.discrepancies[0].direction == "over"


def test_the_tolerance_can_be_tightened():
    lots = [lot()]
    loose = reconcile_room(lots, room(("TR-1", "2024-CHK-01", 9950)))
    tight = reconcile_room(lots, room(("TR-1", "2024-CHK-01", 9950)), tolerance_percent=0)
    assert loose.is_clean
    assert not tight.is_clean


def test_a_negative_tolerance_is_refused():
    with pytest.raises(ValidationError):
        reconcile_room([lot()], room(), tolerance_percent=-1)


def test_a_lot_in_no_vessel_is_reported_separately_from_a_miscount():
    result = reconcile_room([lot()], room(("TR-1", "", 0)))
    assert result.missing_from_vessels == ("2024-CHK-01",)
    assert result.discrepancies == ()


def test_eggs_in_a_tray_belonging_to_nothing_are_reported():
    result = reconcile_room(
        [lot()], room(("TR-1", "2024-CHK-01", 10000), ("TR-2", "2024-COH-09", 500))
    )
    assert result.unknown_in_vessels == ("2024-COH-09",)
    assert not result.is_clean


def test_a_closed_lot_is_not_checked():
    result = reconcile_room([lot(stage=EggStage.PONDED)], room(("TR-1", "", 0)))
    assert result.checked == 0
    assert result.is_clean


def test_the_same_lot_twice_is_refused():
    with pytest.raises(ValidationError):
        reconcile_room([lot(), lot()], room())


def test_the_worst_discrepancy_is_the_biggest_share_not_the_biggest_count():
    lots = [lot(1, green="10000"), lot(2, green="1000")]
    result = reconcile_room(
        lots,
        room(("TR-1", "2024-CHK-01", 9500), ("TR-2", "2024-CHK-02", 500)),
    )
    worst = result.worst
    assert worst is not None
    assert worst.lot == "2024-CHK-02"


def test_the_line_says_all_three_problems():
    result = reconcile_room([lot()], room(("TR-1", "2024-COH-09", 500)))
    line = result.line()
    assert "1 lots checked" in line
    assert "1 not in a vessel" in line
    assert "1 unknown in the room" in line


def test_the_two_totals_of_a_room():
    lots = [lot(1), lot(2, stage=EggStage.PONDED)]
    lots[0].record_loss("2024-10-01", 500, LossCause.PICKED)
    register = room(("TR-1", "2024-CHK-01", 9500))
    assert room_total(register) == Decimal(9500)
    assert record_total(lots) == Decimal(9500)


def test_how_full_the_room_is():
    register = room(("TR-1", "2024-CHK-01", 6000), ("TR-2", "", 0))
    assert occupancy(register) == Decimal("0.25")


def test_a_room_with_nothing_in_it_has_no_share_to_report():
    with pytest.raises(ValidationError):
        occupancy(VesselRegister())


def test_a_jar_without_an_egg_size_is_left_out_of_the_occupancy():
    register = room(("TR-1", "2024-CHK-01", 6000))
    register.add(
        Vessel(
            code="JR-1",
            kind=VesselKind.JAR,
            flow=Quantity(8, "Lpm"),
            volume=Quantity(6, "L"),
        )
    )
    assert occupancy(register) == Decimal("0.5")
    assert occupancy(register, 2000) < Decimal("0.5")
