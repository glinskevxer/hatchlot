from decimal import Decimal

import pytest

from hatchlot.errors import NotFoundError
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.store.db import StoreError, connect, execute
from hatchlot.store.migrations import migrate
from hatchlot.store.repositories import (
    container_count,
    delete_container,
    load_container,
    load_containers,
    load_source,
    load_sources,
    save_container,
    save_containers,
    save_source,
    total_flow_gpm,
)
from hatchlot.store.schema import ALL
from hatchlot.water.source import SourceKind, WaterSource


def database():
    connection = connect()
    migrate(connection, ALL)
    return connection


def source(code="SP-1", flow="900", minimum=None):
    return WaterSource(
        code=code,
        name=f"source {code}",
        kind=SourceKind.SPRING,
        design_flow=Quantity(flow, "gpm"),
        minimum_flow=Quantity(minimum, "gpm") if minimum else None,
    )


def container(code="RW-1", flow="500", water_source="SP-1", out=False):
    return Container(
        code=code,
        kind=ContainerKind.RACEWAY,
        length=Quantity(30, "m"),
        width=Quantity(3, "m"),
        depth=Quantity(1, "m"),
        flow=Quantity(flow, "gpm"),
        water_source=water_source,
        out_of_service=out,
    )


def test_a_water_source_round_trips():
    connection = database()
    save_source(connection, source(minimum="400"))
    back = load_source(connection, "sp 1")
    assert back.name == "source SP-1"
    assert back.kind is SourceKind.SPRING
    assert back.design_flow == Quantity(900, "gpm")
    assert back.minimum_flow == Quantity(400, "gpm")


def test_a_source_with_no_minimum_comes_back_without_one():
    connection = database()
    save_source(connection, source())
    assert load_source(connection, "SP-1").minimum_flow is None


def test_saving_a_source_twice_replaces_it():
    connection = database()
    save_source(connection, source(flow="900"))
    save_source(connection, source(flow="1200"))
    assert load_source(connection, "SP-1").design_flow == Quantity(1200, "gpm")


def test_a_source_that_is_not_there_raises_not_found():
    with pytest.raises(NotFoundError):
        load_source(database(), "SP-9")


def test_the_sources_come_back_as_a_register():
    connection = database()
    save_source(connection, source(code="SP-1"))
    save_source(connection, source(code="WL-1"))
    register = load_sources(connection)
    assert [entry.code for entry in register.all()] == ["SP-1", "WL-1"]


def test_a_container_round_trips_with_its_dimensions():
    connection = database()
    save_source(connection, source())
    save_container(connection, container())
    back = load_container(connection, "rw 1")
    assert back.kind is ContainerKind.RACEWAY
    assert back.volume == Quantity(90, "m3")
    assert back.flow == Quantity(500, "gpm")
    assert back.water_source == "SP-1"
    assert back.is_available()


def test_a_container_out_of_service_comes_back_that_way():
    connection = database()
    save_source(connection, source())
    save_container(connection, container(out=True))
    assert not load_container(connection, "RW-1").is_available()


def test_a_container_with_no_source_is_allowed():
    connection = database()
    save_container(connection, container(water_source=""))
    assert load_container(connection, "RW-1").water_source == ""


def test_a_container_pointing_at_a_source_that_is_not_there_is_refused():
    connection = database()
    with pytest.raises(StoreError):
        save_container(connection, container(water_source="SP-9"))


def test_a_container_that_is_not_there_raises_not_found():
    with pytest.raises(NotFoundError):
        load_container(database(), "RW-9")


def test_a_whole_register_saves_and_loads():
    connection = database()
    save_source(connection, source())
    register = ContainerRegister()
    register.add(container(code="RW-1"))
    register.add(container(code="RW-2", flow="600"))
    assert save_containers(connection, register) == 2
    back = load_containers(connection)
    assert [entry.code for entry in back.all()] == ["RW-1", "RW-2"]
    assert back.get("RW-2").flow == Quantity(600, "gpm")


def test_a_container_can_be_deleted_when_nothing_points_at_it():
    connection = database()
    save_container(connection, container(water_source=""))
    assert delete_container(connection, "RW-1")
    assert container_count(connection) == 0
    assert not delete_container(connection, "RW-1")


def test_a_container_a_lot_is_sitting_in_cannot_be_deleted():
    connection = database()
    save_container(connection, container(water_source=""))
    execute(
        connection,
        "INSERT INTO rearing_lot (code, container, species, ponded_on, population, "
        "mean_weight_g, state) VALUES ('2024-CHK-01', 'RW-1', 'CHK', '2025-01-15', "
        "'1000', '2.5', 'rearing')",
    )
    with pytest.raises(StoreError):
        delete_container(connection, "RW-1")


def test_the_flow_is_added_up_in_the_database():
    connection = database()
    save_container(connection, container(code="RW-1", flow="500", water_source=""))
    save_container(connection, container(code="RW-2", flow="600", water_source=""))
    save_container(connection, container(code="RW-3", flow="700", water_source="", out=True))
    assert total_flow_gpm(connection) == Decimal("1100.0")


def test_an_empty_station_has_no_flow_and_no_containers():
    connection = database()
    assert container_count(connection) == 0
    assert total_flow_gpm(connection) == Decimal(0)
