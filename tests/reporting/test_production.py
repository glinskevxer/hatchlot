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
from hatchlot.rearing.mortality import MortalityLog
from hatchlot.rearing.summary import summarise_rearing
from hatchlot.reporting.production import (
    build_production_report,
    collect_exceptions,
    monthly_windows,
    render_production,
)
from hatchlot.station import StationProfile

MARCH = DateRange("2025-03-01", "2025-03-31")


def containers(flow="500"):
    register = ContainerRegister()
    register.add(
        Container(
            code="RW-1",
            kind=ContainerKind.RACEWAY,
            length=Quantity(30, "m"),
            width=Quantity(3, "m"),
            depth=Quantity(1, "m"),
            flow=Quantity(flow, "gpm"),
        )
    )
    return register


def lot(population="10000", unit="RW-1"):
    return RearingLot(
        code=LotCode(2024, "CHK", 1),
        container=unit,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity("2.5", "g"),
    )


def ledger(count=10000):
    book = Ledger()
    book.record(LedgerEntry("2025-01-15", "2024-CHK-01", EntryKind.PONDED, count, "kt"))
    return book


def cleaned():
    log = CleaningLog()
    log.record(Cleaning("2025-03-28", "RW-1", CleaningMethod.BRUSH, "kt"))
    return log


def parts(population="10000", flow="500", ledger_count=10000, cleaning=None, unit="RW-1"):
    register = containers(flow)
    lots = [lot(population, unit)]
    inventory = take_inventory(lots, register, ledger(ledger_count), "2025-03-31")
    log = cleaned() if cleaning is None else cleaning
    summary = summarise_rearing(inventory, MortalityLog(), log, register, MARCH)
    return inventory, summary


def profile():
    return StationProfile(code="COLD-CREEK", name="Cold Creek")


def test_a_clean_station_reports_no_exceptions():
    inventory, summary = parts()
    report = build_production_report(
        profile(), inventory, summary, Quantity(300, "kg"), "2025-03-31"
    )
    assert report.is_clean
    assert report.lots == 1
    assert report.population == Decimal(10000)


def test_an_overloaded_unit_becomes_an_exception():
    inventory, summary = parts(population="400000", flow="100", ledger_count=400000)
    assert any("loading limit" in line for line in collect_exceptions(inventory, summary))


def test_a_lot_off_its_ledger_becomes_an_exception():
    inventory, summary = parts(ledger_count=9000)
    lines = collect_exceptions(inventory, summary)
    assert any("off its ledger" in line for line in lines)


def test_a_homeless_lot_becomes_an_exception():
    inventory, summary = parts(unit="RW-9")
    assert any("not in any unit" in line for line in collect_exceptions(inventory, summary))


def test_an_uncleaned_unit_becomes_an_exception():
    inventory, summary = parts(cleaning=CleaningLog())
    assert any("overdue a cleaning" in line for line in collect_exceptions(inventory, summary))


def test_the_mean_weight_comes_off_the_biomass_and_the_count():
    inventory, summary = parts()
    report = build_production_report(
        profile(), inventory, summary, Quantity(300, "kg"), "2025-03-31"
    )
    assert report.mean_weight.rounded(2) == Quantity("2.50", "g")


def test_a_station_with_no_fish_has_no_mean_weight_or_conversion():
    register = containers()
    inventory = take_inventory([], register, Ledger(), "2025-03-31")
    summary = summarise_rearing(inventory, MortalityLog(), cleaned(), register, MARCH)
    report = build_production_report(profile(), inventory, summary, Quantity(0, "kg"), "2025-03-31")
    assert report.mean_weight == Quantity(0, "g")
    assert report.conversion is None


def test_the_conversion_is_the_feed_against_the_biomass():
    inventory, summary = parts()
    report = build_production_report(
        profile(), inventory, summary, Quantity(25, "kg"), "2025-03-31"
    )
    assert report.conversion == Decimal(1)


def test_the_rendered_report_has_all_three_parts():
    inventory, summary = parts(ledger_count=9000)
    report = build_production_report(
        profile(), inventory, summary, Quantity(300, "kg"), "2025-03-31"
    )
    text = render_production(report, inventory)
    assert "Production report" in text
    assert "Cold Creek" in text
    assert "2024-CHK-01" in text
    assert "Exceptions" in text


def test_a_clean_report_has_no_exceptions_section():
    inventory, summary = parts()
    report = build_production_report(
        profile(), inventory, summary, Quantity(300, "kg"), "2025-03-31"
    )
    assert "Exceptions" not in render_production(report, inventory)


def test_a_period_splits_into_the_months_it_covers():
    months = monthly_windows(DateRange("2025-01-15", "2025-03-10"))
    assert len(months) == 3
    assert months[0].start == date(2025, 1, 15)
    assert months[0].end == date(2025, 1, 31)
    assert months[-1].end == date(2025, 3, 10)


def test_a_period_inside_one_month_is_one_window():
    months = monthly_windows(MARCH)
    assert len(months) == 1
    assert months[0] == MARCH


def test_a_period_of_years_is_refused():
    with pytest.raises(ValidationError):
        monthly_windows(DateRange("2015-01-01", "2027-01-01"))
