from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, StateError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.eggslot import EggLot, EggStage, LossCause
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind
from hatchlot.rearing.ledger import EntryKind, Ledger
from hatchlot.rearing.lot import RearingLot
from hatchlot.rearing.ponding import check_container_free, pond_lot, ponding_loss


def egg_lot(green="10000", stage=EggStage.HATCHED):
    return EggLot(
        code=LotCode(2024, "CHK", 1),
        take="T-001",
        species="CHK",
        spawned_on=date(2024, 9, 13),
        green_count=Decimal(green),
        stage=stage,
    )


def container(code="RW-1"):
    return Container(
        code=code,
        kind=ContainerKind.RACEWAY,
        length=Quantity(30, "m"),
        width=Quantity(3, "m"),
        depth=Quantity(1, "m"),
        flow=Quantity(500, "gpm"),
    )


def test_ponding_makes_a_rearing_lot_and_closes_the_egg_lot():
    eggs = egg_lot()
    ledger = Ledger()
    rearing, record = pond_lot(
        eggs, container(), ledger, "2025-01-15", 9000, Quantity("0.4", "g"), "kt"
    )
    assert isinstance(rearing, RearingLot)
    assert rearing.population == Decimal(9000)
    assert rearing.container == "RW-1"
    assert rearing.origin_egg_lot == "2024-CHK-01"
    assert eggs.stage is EggStage.PONDED
    assert record.fish == Decimal(9000)


def test_the_ledger_gets_the_opening_entry():
    ledger = Ledger()
    pond_lot(egg_lot(), container(), ledger, "2025-01-15", 9000, Quantity("0.4", "g"), "kt")
    entries = ledger.for_lot("2024-CHK-01")
    assert len(entries) == 1
    assert entries[0].kind is EntryKind.PONDED
    assert ledger.balance("2024-CHK-01").closing == Decimal(9000)


def test_a_lot_that_has_not_hatched_cannot_be_ponded():
    with pytest.raises(StateError):
        pond_lot(
            egg_lot(stage=EggStage.EYED),
            container(),
            Ledger(),
            "2025-01-15",
            9000,
            Quantity("0.4", "g"),
            "kt",
        )


def test_more_fish_than_the_egg_lot_was_carrying_is_refused():
    with pytest.raises(ValidationError):
        pond_lot(
            egg_lot(green="1000"),
            container(),
            Ledger(),
            "2025-01-15",
            2000,
            Quantity("0.4", "g"),
            "kt",
        )


def test_a_ponding_needs_fish_a_weight_a_person_and_a_sane_day():
    eggs = egg_lot()
    with pytest.raises(ValidationError):
        pond_lot(eggs, container(), Ledger(), "2025-01-15", 0, Quantity("0.4", "g"), "kt")
    with pytest.raises(ValidationError):
        pond_lot(eggs, container(), Ledger(), "2025-01-15", 100, Quantity(0, "g"), "kt")
    with pytest.raises(ValidationError):
        pond_lot(eggs, container(), Ledger(), "2025-01-15", 100, Quantity("0.4", "g"), " ")
    with pytest.raises(ValidationError):
        pond_lot(eggs, container(), Ledger(), "2024-01-01", 100, Quantity("0.4", "g"), "kt")


def test_a_unit_out_of_service_cannot_be_ponded_into():
    unit = container()
    unit.take_out_of_service("liner torn")
    with pytest.raises(PolicyError) as excinfo:
        pond_lot(egg_lot(), unit, Ledger(), "2025-01-15", 100, Quantity("0.4", "g"), "kt")
    assert excinfo.value.rule == "container.out_of_service"


def test_the_rearing_lot_can_take_a_code_of_its_own():
    rearing, _ = pond_lot(
        egg_lot(),
        container(),
        Ledger(),
        "2025-01-15",
        9000,
        Quantity("0.4", "g"),
        "kt",
        rearing_code=LotCode(2025, "CHK", 7),
    )
    assert str(rearing.code) == "2025-CHK-07"


def test_the_fish_that_never_made_it_into_the_raceway():
    eggs = egg_lot(green="10000")
    eggs.record_loss("2024-12-01", 500, LossCause.PICKED)
    _, record = pond_lot(
        eggs, container(), Ledger(), "2025-01-15", 9000, Quantity("0.4", "g"), "kt"
    )
    assert ponding_loss(eggs, record) == Decimal(500)
    assert record.biomass == Quantity("3.6000", "kg")


def test_a_ponding_that_lost_nothing_reports_nothing():
    eggs = egg_lot(green="10000")
    _, record = pond_lot(
        eggs, container(), Ledger(), "2025-01-15", 10000, Quantity("0.4", "g"), "kt"
    )
    assert ponding_loss(eggs, record) == Decimal(0)


def test_an_occupied_unit_is_refused_unless_somebody_says_otherwise():
    unit = container()
    sitting = RearingLot(
        code=LotCode(2024, "COH", 1),
        container="RW-1",
        ponded_on=date(2025, 1, 1),
        population=Decimal(100),
        mean_weight=Quantity(1, "g"),
    )
    with pytest.raises(PolicyError) as excinfo:
        check_container_free(unit, [sitting])
    assert excinfo.value.rule == "ponding.occupied"


def test_a_unit_whose_last_lot_has_gone_is_free():
    unit = container()
    gone = RearingLot(
        code=LotCode(2024, "COH", 1),
        container="RW-1",
        ponded_on=date(2025, 1, 1),
        population=Decimal(100),
        mean_weight=Quantity(1, "g"),
    )
    gone.remove(100)
    check_container_free(unit, [gone])
    check_container_free(unit, [])
