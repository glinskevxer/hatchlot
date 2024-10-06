from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.cleaning import Cleaning, CleaningLog, CleaningMethod
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.inventory import take_inventory
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry
from hatchlot.rearing.lot import RearingLot
from hatchlot.rearing.mortality import MortalityCause, MortalityLog, MortalityRecord
from hatchlot.rearing.summary import days_of_feed, projected_biomass, summarise_rearing

MARCH = DateRange("2025-03-01", "2025-03-31")


def containers(*codes, flow="500"):
    register = ContainerRegister()
    for code in codes:
        register.add(
            Container(
                code=code,
                kind=ContainerKind.RACEWAY,
                length=Quantity(30, "m"),
                width=Quantity(3, "m"),
                depth=Quantity(1, "m"),
                flow=Quantity(flow, "gpm"),
            )
        )
    return register


def lot(sequence=1, population="10000", grams="2.5", unit="RW-1"):
    return RearingLot(
        code=LotCode(2024, "CHK", sequence),
        container=unit,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity(grams, "g"),
    )


def ledger_for(*pairs):
    book = Ledger()
    for code, count in pairs:
        book.record(LedgerEntry("2025-01-15", code, EntryKind.PONDED, count, "kt"))
    return book


def inventory_of(lots, register):
    return take_inventory(
        lots,
        register,
        ledger_for(*[(str(entry.code), entry.population) for entry in lots]),
        "2025-03-31",
    )


def mortality_of(*records):
    log = MortalityLog()
    for day, count, cause in records:
        log.record(MortalityRecord(day, "2024-CHK-01", count, cause, "kt"))
    return log


def cleaned_on(*days):
    log = CleaningLog()
    for day in days:
        log.record(Cleaning(day, "RW-1", CleaningMethod.BRUSH, "kt"))
    return log


def test_a_quiet_month_reads_quiet():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register), MortalityLog(), cleaned_on("2025-03-28"), register, MARCH
    )
    assert summary.lots == 1
    assert summary.dead == Decimal(0)
    assert summary.mortality_rate == Decimal(0)
    assert summary.survival == Decimal(1)
    assert not summary.needs_attention
    assert summary.worst_cause is None


def test_the_mortality_rate_is_against_the_fish_that_were_there():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot(population="9900")], register),
        mortality_of(("2025-03-05", 100, MortalityCause.DISEASE)),
        cleaned_on("2025-03-28"),
        register,
        MARCH,
    )
    assert summary.dead == Decimal(100)
    assert summary.mortality_rate == Decimal("0.01")


def test_deaths_outside_the_window_are_not_counted():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register),
        mortality_of(("2025-01-05", 500, MortalityCause.DISEASE)),
        cleaned_on("2025-03-28"),
        register,
        MARCH,
    )
    assert summary.dead == Decimal(0)


def test_the_worst_cause_and_the_preventable_share():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register),
        mortality_of(
            ("2025-03-05", 300, MortalityCause.OXYGEN),
            ("2025-03-06", 100, MortalityCause.PREDATION),
        ),
        cleaned_on("2025-03-28"),
        register,
        MARCH,
    )
    assert summary.worst_cause is MortalityCause.OXYGEN
    assert summary.preventable_share == Decimal("0.75")


def test_an_overloaded_unit_and_an_unclean_one_both_want_attention():
    register = containers("RW-1", flow="100")
    summary = summarise_rearing(
        inventory_of([lot(population="400000")], register),
        MortalityLog(),
        CleaningLog(),
        register,
        MARCH,
    )
    assert summary.overloaded == ("RW-1",)
    assert summary.overdue_cleaning == ("RW-1",)
    assert summary.needs_attention


def test_a_unit_the_station_does_not_have_is_not_a_cleaning_problem():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot(unit="RW-9")], register),
        MortalityLog(),
        CleaningLog(),
        register,
        MARCH,
    )
    assert summary.overdue_cleaning == ()


def test_a_single_day_window_is_a_perfectly_good_summary():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register),
        mortality_of(("2025-03-05", 100, MortalityCause.DISEASE)),
        cleaned_on("2025-03-04"),
        register,
        DateRange("2025-03-05", "2025-03-05"),
    )
    assert summary.dead == Decimal(100)


def test_the_line_reads_like_a_morning_report():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register), MortalityLog(), cleaned_on("2025-03-28"), register, MARCH
    )
    assert "1 lots" in summary.line()
    assert "0.00% lost" in summary.line()


def test_what_the_station_will_be_carrying_in_a_month():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register), MortalityLog(), cleaned_on("2025-03-28"), register, MARCH
    )
    assert projected_biomass(summary, "0.02", 30) > summary.biomass
    assert projected_biomass(summary, "0.02", 0) == summary.biomass
    with pytest.raises(ValidationError):
        projected_biomass(summary, "0.02", -1)
    with pytest.raises(ValidationError):
        projected_biomass(summary, 0, 30)


def test_how_long_the_feed_store_lasts():
    register = containers("RW-1")
    summary = summarise_rearing(
        inventory_of([lot()], register), MortalityLog(), cleaned_on("2025-03-28"), register, MARCH
    )
    assert days_of_feed(summary, Quantity(100, "kg"), "0.02") == 200
    with pytest.raises(ValidationError):
        days_of_feed(summary, Quantity(100, "kg"), 0)
