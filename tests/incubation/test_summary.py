from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation import EggLot, EggStage, LossCause
from hatchlot.incubation.summary import expected_standing, summarise_room
from hatchlot.incubation.vessel import Vessel, VesselKind, VesselRegister
from hatchlot.quantities.base import Quantity
from hatchlot.water.thermal import ThermalSeries


def lot(sequence=1, green="10000", stage=EggStage.GREEN):
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
                    capacity_eggs=Decimal(20000),
                )
            )
        if lot_code:
            register.get(code).load(lot_code, eggs)
    return register


def steady(days=250, celsius="10"):
    series = ThermalSeries()
    start = date(2024, 9, 13)
    for offset in range(days):
        series.add(date.fromordinal(start.toordinal() + offset), celsius)
    return series


def test_a_room_summary_counts_the_live_lots_only():
    lots = [lot(1), lot(2, stage=EggStage.PONDED)]
    summary = summarise_room(lots, room(("TR-1", "2024-CHK-01", 10000)), steady(), "2024-10-01")
    assert summary.lots == 1
    assert summary.eggs == Decimal(10000)
    assert summary.survival == Decimal(1)


def test_the_eggs_are_split_by_the_stage_the_lots_are_in():
    lots = [lot(1), lot(2, stage=EggStage.EYED, green="5000")]
    summary = summarise_room(
        lots,
        room(("TR-1", "2024-CHK-01", 10000), ("TR-2", "2024-CHK-02", 5000)),
        steady(),
        "2024-10-01",
    )
    assert summary.by_stage[EggStage.GREEN] == Decimal(10000)
    assert summary.by_stage[EggStage.EYED] == Decimal(5000)


def test_the_survival_is_across_the_live_lots():
    eggs = lot()
    eggs.record_loss("2024-09-20", 2000, LossCause.UNFERTILISED)
    summary = summarise_room([eggs], room(("TR-1", "2024-CHK-01", 8000)), steady(), "2024-10-01")
    assert summary.survival == Decimal("0.8")


def test_a_room_of_nothing_has_no_survival_to_report():
    summary = summarise_room([], VesselRegister(), steady(), "2024-10-01")
    assert summary.survival == Decimal(0)
    assert summary.eggs == Decimal(0)


def test_the_week_ahead_holds_only_what_lands_in_it():
    lots = [lot()]
    register = room(("TR-1", "2024-CHK-01", 10000))
    quiet = summarise_room(lots, register, steady(), "2024-10-01")
    busy = summarise_room(lots, register, steady(), "2024-10-21")
    assert quiet.coming_week == ()
    assert len(busy.coming_week) == 1
    assert busy.eggs_moving == Decimal(10000)


def test_the_reconciliation_rides_along_with_the_summary():
    lots = [lot()]
    clean = summarise_room(lots, room(("TR-1", "2024-CHK-01", 10000)), steady(), "2024-10-01")
    dirty = summarise_room(lots, room(("TR-1", "2024-CHK-01", 8000)), steady(), "2024-10-01")
    assert clean.is_clean
    assert not dirty.is_clean
    assert "clean" in clean.line()
    assert "needs a count" in dirty.line()


def test_the_tolerance_carries_through_to_the_reconciliation():
    lots = [lot()]
    register = room(("TR-1", "2024-CHK-01", 9950))
    assert summarise_room(lots, register, steady(), "2024-10-01").is_clean
    assert not summarise_room(lots, register, steady(), "2024-10-01", tolerance_percent=0).is_clean


def test_the_expected_standing_against_the_usual_losses():
    lots = [lot(1, green="10000"), lot(2, green="10000", stage=EggStage.PONDED)]
    assert expected_standing(lots) == Decimal(8500)
    assert expected_standing(lots, "0.5") == Decimal(5000)


def test_an_impossible_expected_survival_is_refused():
    with pytest.raises(ValidationError):
        expected_standing([lot()], "1.2")
    with pytest.raises(ValidationError):
        expected_standing([lot()], "-0.1")
