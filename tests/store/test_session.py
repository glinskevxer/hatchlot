from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import NotFoundError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.lot import RearingLot
from hatchlot.station import StationProfile
from hatchlot.store.db import StoreError
from hatchlot.store.schema import latest_version
from hatchlot.store.session import open_session, session
from hatchlot.units import System
from hatchlot.water.source import SourceKind, SourceRegister, WaterSource


def sources():
    register = SourceRegister()
    register.add(
        WaterSource(
            code="SP-1",
            name="upper spring",
            kind=SourceKind.SPRING,
            design_flow=Quantity(900, "gpm"),
        )
    )
    return register


def containers(*codes):
    register = ContainerRegister()
    for code in codes or ("RW-1",):
        register.add(
            Container(
                code=code,
                kind=ContainerKind.RACEWAY,
                length=Quantity(30, "m"),
                width=Quantity(3, "m"),
                depth=Quantity(1, "m"),
                flow=Quantity(500, "gpm"),
                water_source="SP-1",
            )
        )
    return register


def lot(sequence=1, container="RW-1"):
    return RearingLot(
        code=LotCode(2024, "CHK", sequence),
        container=container,
        ponded_on=date(2025, 1, 15),
        population=Decimal(50000),
        mean_weight=Quantity("2.5", "g"),
    )


def profile():
    return StationProfile(
        code="COLD-CREEK",
        name="Cold Creek",
        system=System.METRIC,
        elevation_m=Decimal(800),
    )


def test_a_new_session_comes_up_migrated():
    with session() as opened:
        assert opened.version == latest_version()
        assert opened.is_current


def test_a_session_can_be_opened_without_migrating():
    opened = open_session(migrate_to_latest=False)
    assert opened.version == 0
    assert not opened.is_current
    opened.close()


def test_the_station_saves_in_one_go_and_comes_back():
    with session() as opened:
        assert opened.save_station(sources(), containers("RW-1", "RW-2")) == (1, 2)
        assert len(opened.containers()) == 2
        assert len(opened.sources()) == 1
        assert opened.containers().get("RW-1").water_source == "SP-1"


def test_a_station_whose_containers_point_at_missing_water_saves_nothing():
    with session() as opened:
        broken = ContainerRegister()
        broken.add(
            Container(
                code="RW-1",
                kind=ContainerKind.RACEWAY,
                length=Quantity(30, "m"),
                width=Quantity(3, "m"),
                depth=Quantity(1, "m"),
                flow=Quantity(500, "gpm"),
                water_source="SP-9",
            )
        )
        with pytest.raises(StoreError):
            opened.save_station(SourceRegister(), broken)
        assert len(opened.containers()) == 0


def test_lots_save_and_come_back_live_only_by_default():
    with session() as opened:
        opened.save_station(sources(), containers())
        gone = lot(2)
        gone.remove(gone.population)
        assert opened.save_lots([lot(1), gone]) == 2
        assert len(opened.lots()) == 1
        assert len(opened.lots(live_only=False)) == 2


def test_the_ledger_comes_back_off_the_session():
    with session() as opened:
        assert len(opened.ledger()) == 0


def test_the_profile_round_trips():
    with session() as opened:
        opened.save_profile(profile())
        back = opened.profile()
        assert back == profile()
        assert back.is_metric


def test_saving_the_profile_twice_replaces_it():
    with session() as opened:
        opened.save_profile(profile())
        opened.save_profile(StationProfile(code="COLD-CREEK", name="Cold Creek Two"))
        assert opened.profile().name == "Cold Creek Two"


def test_a_database_with_no_profile_has_none_to_load():
    with session() as opened, pytest.raises(NotFoundError):
        opened.profile()


def test_two_profiles_have_to_be_asked_for_by_name():
    with session() as opened:
        opened.save_profile(profile())
        opened.save_profile(StationProfile(code="OTHER", name="Other"))
        with pytest.raises(ValidationError):
            opened.profile()
        assert opened.profile("OTHER").name == "Other"


def test_a_profile_that_is_not_there_raises_not_found():
    with session() as opened:
        opened.save_profile(profile())
        with pytest.raises(NotFoundError):
            opened.profile("NOWHERE")


def test_a_session_survives_being_closed_and_reopened(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    with session(path) as opened:
        opened.save_station(sources(), containers())
        opened.save_profile(profile())
    with session(path) as reopened:
        assert reopened.is_current
        assert len(reopened.containers()) == 1
        assert reopened.profile().code == "COLD-CREEK"
