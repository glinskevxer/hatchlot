"""A whole brood year, walked through the engine the way a station would.

This is the test that catches the joins. Each module has its own tests and they
all pass on their own; what this checks is that a lot can actually get from a
spawn take to a truck without something in the middle refusing a shape that the
module before it produces.
"""

from datetime import date, timedelta
from decimal import Decimal

from hatchlot.brood.cross import CrossDesign, plan_cross
from hatchlot.brood.eggcount import CountMethod, EggEstimate
from hatchlot.brood.female import BroodFemale, Ripeness
from hatchlot.brood.register import BroodRegister, summarise_season
from hatchlot.brood.take import SpawnTake, TakeRegister
from hatchlot.calendar import DateRange
from hatchlot.distribution.haul import HaulLoad, OxygenSupply, Tank
from hatchlot.distribution.release import ReleaseKind, ReleaseRegister, release_fish
from hatchlot.distribution.request import StockingRequest
from hatchlot.identifiers import LotCode
from hatchlot.incubation.development import Mark, milestone
from hatchlot.incubation.eggslot import EggLot, EggStage, LossCause
from hatchlot.incubation.shock import fertility, shock
from hatchlot.incubation.vessel import Vessel, VesselKind, VesselRegister
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.ledger import Ledger
from hatchlot.rearing.loading import LoadingStatus, assess
from hatchlot.rearing.ponding import pond_lot
from hatchlot.species import species
from hatchlot.water.thermal import ThermalSeries

CHINOOK = species("CHK")
SPAWN_DAY = date(2024, 9, 13)


def water(start=SPAWN_DAY, days=600, celsius="10"):
    series = ThermalSeries()
    for offset in range(days):
        series.add(start + timedelta(days=offset), celsius)
    return series


def brood_register(count=6):
    register = BroodRegister()
    for index in range(count):
        register.add(
            BroodFemale(
                tag=f"F-{index:03d}",
                species="CHK",
                length=Quantity(78, "cm"),
                weight=Quantity("5.4", "kg"),
            )
        )
        register.get(f"F-{index:03d}").check(SPAWN_DAY, Ripeness.RIPE, "kt")
    return register


def take_of(register, eggs=30000):
    take = SpawnTake(
        code="T-001",
        day=SPAWN_DAY,
        species="CHK",
        water=Temperature(11, "C"),
        spawned_by="kt",
    )
    for female in register.all():
        take.add_female(female.tag)
        female.check(SPAWN_DAY, Ripeness.SPAWNED, "kt")
    take.add_male("M-001")
    take.close(EggEstimate(eggs, CountMethod.VON_BAYER))
    take.release("hatchery manager")
    return take


def test_a_take_becomes_an_egg_lot_and_eyes_up_on_the_water_record():
    register = brood_register()
    take = take_of(register)
    eggs = EggLot(
        code=LotCode(2024, "CHK", 1),
        take=take.code,
        species=take.species,
        spawned_on=take.day,
        green_count=take.green_eggs,
    )
    series = water()
    eye_up = milestone(series, eggs.spawned_on, CHINOOK, Mark.EYE_UP)
    assert eye_up.is_reached
    assert eye_up.day is not None
    assert eye_up.day > SPAWN_DAY


def test_the_whole_run_from_spawning_to_release():
    register = brood_register()
    take = take_of(register, eggs=30000)
    takes = TakeRegister()
    takes.add(take)
    season = summarise_season(register, takes, DateRange("2024-09-01", "2024-11-30"), 25000)
    assert season.is_target_met

    eggs = EggLot(
        code=LotCode(2024, "CHK", 1),
        take=take.code,
        species=take.species,
        spawned_on=take.day,
        green_count=take.green_eggs,
    )
    room = VesselRegister()
    room.add(
        Vessel(
            code="TR-1",
            kind=VesselKind.TRAY,
            flow=Quantity(20, "Lpm"),
            capacity_eggs=Decimal(40000),
        )
    )
    room.get("TR-1").load(str(eggs.code), eggs.count)
    eggs.record_loss("2024-09-20", 1500, LossCause.UNFERTILISED)

    series = water()
    eye_up = milestone(series, eggs.spawned_on, CHINOOK, Mark.EYE_UP)
    assert eye_up.day is not None
    result = shock(eggs, eye_up.day, 26000, CHINOOK, CHINOOK.eye_up_units)
    assert eggs.stage is EggStage.EYED
    assert fertility(result, eggs.green_count) > Decimal("0.8")

    hatch = milestone(series, eggs.spawned_on, CHINOOK, Mark.HATCH)
    assert hatch.day is not None
    eggs.advance(EggStage.HATCHED)

    containers = ContainerRegister()
    containers.add(
        Container(
            code="RW-1",
            kind=ContainerKind.RACEWAY,
            length=Quantity(30, "m"),
            width=Quantity(3, "m"),
            depth=Quantity(1, "m"),
            flow=Quantity(500, "gpm"),
        )
    )
    ledger = Ledger()
    swim_up = milestone(series, eggs.spawned_on, CHINOOK, Mark.SWIM_UP)
    assert swim_up.day is not None
    lot, ponding = pond_lot(
        eggs,
        containers.get("RW-1"),
        ledger,
        swim_up.day,
        eggs.count,
        Quantity("0.4", "g"),
        "kt",
    )
    assert ponding.fish == lot.population
    assert ledger.balance(str(lot.code)).closing == lot.population

    lot.resize(Quantity(20, "g"))
    loading = assess(containers.get("RW-1"), lot)
    assert loading.status is not LoadingStatus.OVER

    request = StockingRequest(
        code="SR-001",
        water="LAKE-A",
        species="CHK",
        fish=lot.population,
        target_weight=Quantity(20, "g"),
        window=DateRange("2026-04-01", "2026-05-31"),
        requested_by="district biologist",
    )
    haul = HaulLoad(
        code="HL-001",
        tanks=[Tank(code="TK-1", volume=Quantity(6000, "L"), supply=OxygenSupply.BOTTLED)],
        fish=Decimal(20000),
        mean_weight=lot.mean_weight,
        hours=Decimal(3),
        load_water=Temperature(10, "C"),
        driver="jt",
    )
    releases = ReleaseRegister()
    releases.record(
        release_fish(
            request,
            haul,
            code="RL-001",
            day="2026-04-15",
            lot=str(lot.code),
            kind=ReleaseKind.DIRECT,
            released_by="kt",
            receiving_water=Temperature(11, "C"),
        )
    )
    assert releases.fish_released(str(lot.code)) == Decimal(20000)
    assert request.outstanding == lot.population - Decimal(20000)


def test_the_numbers_survive_the_whole_way_through():
    register = brood_register()
    take = take_of(register, eggs=30000)
    eggs = EggLot(
        code=LotCode(2024, "CHK", 1),
        take=take.code,
        species=take.species,
        spawned_on=take.day,
        green_count=take.green_eggs,
    )
    eggs.record_loss("2024-09-20", 3000, LossCause.UNFERTILISED)
    series = water()
    eye_up = milestone(series, eggs.spawned_on, CHINOOK, Mark.EYE_UP)
    assert eye_up.day is not None
    shock(eggs, eye_up.day, 25000, CHINOOK, CHINOOK.eye_up_units)
    eggs.advance(EggStage.HATCHED)
    containers = ContainerRegister()
    containers.add(
        Container(
            code="RW-1",
            kind=ContainerKind.RACEWAY,
            length=Quantity(30, "m"),
            width=Quantity(3, "m"),
            depth=Quantity(1, "m"),
            flow=Quantity(500, "gpm"),
        )
    )
    lot, _ = pond_lot(
        eggs,
        containers.get("RW-1"),
        Ledger(),
        "2025-01-15",
        24000,
        Quantity("0.4", "g"),
        "kt",
    )
    assert eggs.green_count == Decimal(30000)
    assert eggs.lost_to(LossCause.UNFERTILISED) == Decimal(3000)
    assert eggs.lost_to(LossCause.SHOCK) == Decimal(2000)
    assert lot.population == Decimal(24000)


def test_a_cross_plan_and_the_take_agree_on_the_fish():
    register = brood_register(count=4)
    plan = plan_cross(
        CrossDesign.FACTORIAL,
        [female.tag for female in register.all()],
        ["M-001", "M-002"],
    )
    take = take_of(register)
    assert plan.family_count == 8
    assert set(plan.dams) == set(take.females)
