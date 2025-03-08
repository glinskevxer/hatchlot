from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from hatchlot.calendar import DateRange
from hatchlot.distribution.haul import HaulLoad, OxygenSupply, Tank
from hatchlot.distribution.release import (
    Release,
    ReleaseKind,
    ReleaseRegister,
    release_fish,
)
from hatchlot.distribution.request import StockingRequest
from hatchlot.errors import PolicyError, ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature

SPRING = DateRange("2025-04-01", "2025-05-31")
LOT = "2024-CHK-01"


def request(code="SR-001", fish="20000", grams="20"):
    return StockingRequest(
        code=code,
        water="LAKE-A",
        species="CHK",
        fish=Decimal(fish),
        target_weight=Quantity(grams, "g"),
        window=SPRING,
        requested_by="biologist",
    )


def haul(fish="10000", grams="20", celsius="10"):
    return HaulLoad(
        code="HL-001",
        tanks=[Tank(code="TK-1", volume=Quantity(3000, "L"), supply=OxygenSupply.BOTTLED)],
        fish=Decimal(fish),
        mean_weight=Quantity(grams, "g"),
        hours=Decimal(4),
        load_water=Temperature(celsius, "C"),
        driver="jt",
    )


def do_release(**overrides: Any) -> Release:
    arguments: dict[str, Any] = {
        "code": "RL-001",
        "day": "2025-04-15",
        "lot": LOT,
        "kind": ReleaseKind.DIRECT,
        "released_by": "kt",
        "receiving_water": Temperature(11, "C"),
    }
    arguments.update(overrides)
    ask: StockingRequest = arguments.pop("request", None) or request()
    load: HaulLoad = arguments.pop("haul", None) or haul()
    return release_fish(ask, load, **arguments)


def test_a_release_that_passes_every_gate_is_recorded():
    entry = do_release()
    assert entry.code == "RL-001"
    assert entry.water == "LAKE-A"
    assert entry.fish == Decimal(10000)
    assert entry.biomass == Quantity("200.000", "kg")
    assert entry.was_tempered


def test_the_request_is_delivered_against():
    ask = request(fish="20000")
    do_release(request=ask)
    assert ask.delivered == Decimal(10000)
    assert ask.outstanding == Decimal(10000)


def test_a_health_hold_stops_it_before_anything_else():
    with pytest.raises(PolicyError) as excinfo:
        do_release(health_hold=True, receiving_water=Temperature(30, "C"))
    assert excinfo.value.rule == "release.health_hold"


def test_an_outstanding_withdrawal_stops_it():
    with pytest.raises(PolicyError) as excinfo:
        do_release(withdrawal_clear=False)
    assert excinfo.value.rule == "release.withdrawal"


def test_a_marking_run_nobody_accepted_stops_it():
    with pytest.raises(PolicyError) as excinfo:
        do_release(marking_accepted=False)
    assert excinfo.value.rule == "release.marking"


def test_a_closed_request_stops_it():
    ask = request()
    ask.decline("water is closed")
    with pytest.raises(PolicyError) as excinfo:
        do_release(request=ask)
    assert excinfo.value.rule == "release.request_closed"


def test_a_day_outside_the_window_stops_it():
    with pytest.raises(PolicyError) as excinfo:
        do_release(day="2025-07-01")
    assert excinfo.value.rule == "release.window"


def test_a_fish_the_request_will_not_take_stops_it():
    with pytest.raises(PolicyError) as excinfo:
        do_release(haul=haul(grams="60"))
    assert excinfo.value.rule == "release.size"


def test_an_overloaded_truck_stops_it():
    with pytest.raises(PolicyError) as excinfo:
        do_release(haul=haul(fish="40000"))
    assert excinfo.value.rule == "haul.overloaded"


def test_an_untempered_release_stops_it():
    with pytest.raises(PolicyError) as excinfo:
        do_release(receiving_water=Temperature(16, "C"))
    assert excinfo.value.rule == "haul.tempering"


def test_the_tempering_limit_can_be_widened_deliberately():
    entry = do_release(receiving_water=Temperature(15, "C"), tempering_limit=6)
    assert entry.was_tempered


def test_a_release_record_needs_a_person_a_kind_and_fish():
    with pytest.raises(ValidationError):
        Release(
            code="RL-1",
            day=date(2025, 4, 15),
            lot=LOT,
            water="LAKE-A",
            request="SR-001",
            fish=Decimal(100),
            mean_weight=Quantity(20, "g"),
            kind=ReleaseKind.DIRECT,
            released_by="  ",
        )
    with pytest.raises(ValidationError):
        Release(
            code="RL-1",
            day=date(2025, 4, 15),
            lot=LOT,
            water="LAKE-A",
            request="SR-001",
            fish=Decimal(0),
            mean_weight=Quantity(20, "g"),
            kind=ReleaseKind.DIRECT,
            released_by="kt",
        )
    with pytest.raises(ValidationError):
        Release(
            code="RL-1",
            day=date(2025, 4, 15),
            lot=LOT,
            water="LAKE-A",
            request="SR-001",
            fish=Decimal(100),
            mean_weight=Quantity(20, "g"),
            kind="direct",  # type: ignore[arg-type]
            released_by="kt",
        )


def test_a_transfer_is_not_a_release_into_a_fishery():
    assert ReleaseKind.DIRECT.is_final
    assert not ReleaseKind.TRANSFER.is_final


def test_the_register_totals_only_the_final_releases():
    register = ReleaseRegister()
    register.record(do_release())
    register.record(
        do_release(code="RL-002", request=request(code="SR-002"), kind=ReleaseKind.TRANSFER)
    )
    assert register.fish_released() == Decimal(10000)
    assert register.biomass_released() == Quantity("200.000", "kg")
    assert len(register.all()) == 2


def test_the_register_slices_by_lot_water_and_request():
    register = ReleaseRegister()
    register.record(do_release())
    assert len(register.for_lot(LOT)) == 1
    assert len(register.for_water("lake a")) == 1
    assert len(register.for_request("SR-001")) == 1
    assert register.waters() == ("LAKE-A",)
    assert register.fish_released(LOT) == Decimal(10000)
    assert register.biomass_released(LOT) == Quantity("200.000", "kg")


def test_a_release_with_no_tempering_record_shows_up_as_a_finding():
    register = ReleaseRegister()
    register.record(
        Release(
            code="RL-009",
            day=date(2025, 4, 15),
            lot=LOT,
            water="LAKE-A",
            request="SR-001",
            fish=Decimal(100),
            mean_weight=Quantity(20, "g"),
            kind=ReleaseKind.DIRECT,
            released_by="kt",
        )
    )
    assert len(register.untempered()) == 1


def test_the_fish_per_pound_on_the_release_record():
    entry = do_release()
    assert entry.fish_per_pound.quantize(Decimal("0.01")) == Decimal("22.68")
