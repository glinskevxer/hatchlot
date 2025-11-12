"""A rearing year: feed in, growth out, and the two records agreeing at the end.

The season walk covers the handovers between stages. This one stays inside the
rearing year and joins the parts that run at the same time rather than one after
the other: the feeding record, the growth history, the mortality log and the
ledger, over one lot, for nine months.
"""

from datetime import date, timedelta
from decimal import Decimal

from hatchlot.calendar import DateRange
from hatchlot.feed.conversion import Conversion, combined
from hatchlot.feed.feeding import Feeding, FeedingLog, FeedMethod
from hatchlot.feed.ration import feeding_rate
from hatchlot.growth.history import GrowthHistory, WeighIn
from hatchlot.growth.model import GrowthModel
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.rearing.cleaning import Cleaning, CleaningLog, CleaningMethod
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.inventory import take_inventory
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry
from hatchlot.rearing.lot import RearingLot
from hatchlot.rearing.mortality import MortalityCause, MortalityLog, MortalityRecord
from hatchlot.rearing.summary import summarise_rearing
from hatchlot.water.thermal import ThermalSeries

START = date(2025, 1, 15)
MONTHS = 9
MODEL = GrowthModel(coefficient=Decimal("0.7"))
LOT = "2024-CHK-01"


def containers():
    register = ContainerRegister()
    register.add(
        Container(
            code="RW-1",
            kind=ContainerKind.RACEWAY,
            length=Quantity(30, "m"),
            width=Quantity(3, "m"),
            depth=Quantity(1, "m"),
            flow=Quantity(600, "gpm"),
        )
    )
    return register


def water(days=300, celsius="10"):
    series = ThermalSeries()
    for offset in range(days):
        series.add(START + timedelta(days=offset), celsius)
    return series


def run_year():
    """Feed and grow one lot for nine months, writing every register as it goes."""

    lot = RearingLot(
        code=LotCode(2024, "CHK", 1),
        container="RW-1",
        ponded_on=START,
        population=Decimal(50000),
        mean_weight=Quantity("0.5", "g"),
    )
    ledger = Ledger()
    ledger.record(LedgerEntry(START, LOT, EntryKind.PONDED, lot.population, "kt"))
    feeding = FeedingLog()
    mortality = MortalityLog()
    history = GrowthHistory()
    history.record(WeighIn(START, LOT, lot.mean_weight))
    temperature = Temperature(10, "C")
    day = START
    for month in range(MONTHS):
        day = START + timedelta(days=30 * (month + 1))
        rate = feeding_rate(lot.mean_weight, temperature)
        fed = Quantity(lot.biomass.to("kg").amount * rate / Decimal(100) * Decimal(30), "kg")
        feeding.record(Feeding(day, LOT, fed, FeedMethod.HAND, f"FL-{month:03d}", "kt"))
        dead = Decimal(200)
        mortality.record(MortalityRecord(day, LOT, dead, MortalityCause.UNKNOWN, "kt"))
        lot.remove(dead)
        ledger.record(LedgerEntry(day, LOT, EntryKind.MORTALITY, dead, "kt", "background loss"))
        lot.resize(MODEL.grow(lot.mean_weight, Decimal(300)))
        history.record(WeighIn(day, LOT, lot.mean_weight))
    return lot, ledger, feeding, mortality, history, day


def test_the_lot_grows_and_the_two_records_still_agree():
    lot, ledger, _, _, _, _ = run_year()
    assert Quantity(10, "g") < lot.mean_weight < Quantity(40, "g")
    assert lot.population == Decimal(50000 - 200 * MONTHS)
    assert ledger.balance(LOT).closing == lot.population


def test_the_growth_history_recovers_the_model_it_was_grown_on():
    _, _, _, _, history, _ = run_year()
    fitted = history.observed_model(LOT, water())
    assert abs(fitted.coefficient - MODEL.coefficient) < Decimal("0.05")
    assert not history.has_stalled(LOT)


def test_the_feed_conversion_over_the_year_is_believable():
    lot, _, feeding, mortality, history, last = run_year()
    window = DateRange(START, last)
    opening = Quantity(Decimal(50000) * Decimal("0.5") / Decimal(1000), "kg")
    period = Conversion(
        fed=feeding.fed(LOT, window),
        opening_biomass=opening,
        closing_biomass=lot.biomass,
        mortality_biomass=Quantity(
            mortality.total(LOT, window) * lot.mean_weight.to("kg").amount, "kg"
        ),
    )
    assert period.gain > Quantity(0, "kg")
    assert period.is_plausible(ceiling=3)
    assert period.biological_ratio < period.economic_ratio


def test_the_month_by_month_conversions_combine_into_the_year():
    lot, _, feeding, _, _, last = run_year()
    window = DateRange(START, last)
    whole = Conversion(
        fed=feeding.fed(LOT, window),
        opening_biomass=Quantity(25, "kg"),
        closing_biomass=lot.biomass,
        mortality_biomass=Quantity(0, "kg"),
    )
    halves = [
        Conversion(
            fed=Quantity(whole.fed.to("kg").amount / 2, "kg"),
            opening_biomass=Quantity(25, "kg"),
            closing_biomass=Quantity(200, "kg"),
            mortality_biomass=Quantity(0, "kg"),
        ),
        Conversion(
            fed=Quantity(whole.fed.to("kg").amount / 2, "kg"),
            opening_biomass=Quantity(200, "kg"),
            closing_biomass=lot.biomass,
            mortality_biomass=Quantity(0, "kg"),
        ),
    ]
    assert combined(halves).economic_ratio == whole.economic_ratio


def test_the_year_end_inventory_is_clean_and_the_unit_is_still_inside_its_limit():
    lot, ledger, _, mortality, _, last = run_year()
    register = containers()
    inventory = take_inventory([lot], register, ledger, last)
    assert inventory.is_clean
    cleaning = CleaningLog()
    cleaning.record(Cleaning(last, "RW-1", CleaningMethod.BRUSH, "kt"))
    summary = summarise_rearing(inventory, mortality, cleaning, register, DateRange(START, last))
    assert summary.overloaded == ()
    assert summary.overdue_cleaning == ()
    assert summary.mortality_rate < Decimal("0.05")


def test_the_mortality_all_landed_in_one_cause_and_none_of_it_was_preventable():
    _, _, _, mortality, _, last = run_year()
    window = DateRange(START, last)
    split = mortality.by_cause(LOT, window)
    assert set(split) == {MortalityCause.UNKNOWN}
    assert mortality.preventable_share(LOT) == Decimal(0)
