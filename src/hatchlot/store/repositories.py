"""Repositories: turning rows into the objects the engine works on.

Two rules run through all of these. Nothing in the engine knows about SQL, and
nothing in here knows about rules. A repository loads and saves; it does not
decide whether a lot may move or whether a raceway is overloaded, and when it is
tempted to, the temptation is a sign the rule belongs somewhere else.

Saving is upsert rather than insert, because the caller almost always has the
whole object and wants the database to match it. An insert-only repository
pushes that decision out to every caller, and they get it wrong differently.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ..errors import NotFoundError
from ..identifiers import normalise_code
from ..quantities.base import Quantity
from ..rearing.container import Container, ContainerKind, ContainerRegister
from ..water.source import SourceKind, SourceRegister, WaterSource
from .db import execute, query, query_one


def save_source(connection: sqlite3.Connection, source: WaterSource) -> str:
    """Write a water source, replacing whatever was under that code."""

    execute(
        connection,
        """
        INSERT INTO water_source (code, name, kind, design_flow_gpm, minimum_flow_gpm)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (code) DO UPDATE SET
            name = excluded.name,
            kind = excluded.kind,
            design_flow_gpm = excluded.design_flow_gpm,
            minimum_flow_gpm = excluded.minimum_flow_gpm
        """,
        source.code,
        source.name,
        source.kind.value,
        source.design_flow.to("gpm").amount,
        source.minimum_flow.to("gpm").amount if source.minimum_flow is not None else None,
    )
    return source.code


def _source_from(row: sqlite3.Row) -> WaterSource:
    minimum = row["minimum_flow_gpm"]
    return WaterSource(
        code=str(row["code"]),
        name=str(row["name"]),
        kind=SourceKind(str(row["kind"])),
        design_flow=Quantity(row["design_flow_gpm"], "gpm"),
        minimum_flow=Quantity(minimum, "gpm") if minimum is not None else None,
    )


def load_source(connection: sqlite3.Connection, code: str) -> WaterSource:
    key = normalise_code(code, field="source")
    row = query_one(connection, "SELECT * FROM water_source WHERE code = ?", key)
    if row is None:
        raise NotFoundError("water source", key)
    return _source_from(row)


def load_sources(connection: sqlite3.Connection) -> SourceRegister:
    """Every water source, back in the register the engine uses."""

    register = SourceRegister()
    for row in query(connection, "SELECT * FROM water_source ORDER BY code"):
        register.add(_source_from(row))
    return register


def save_container(connection: sqlite3.Connection, container: Container) -> str:
    execute(
        connection,
        """
        INSERT INTO container (
            code, kind, length_m, width_m, depth_m, flow_gpm, water_source, out_of_service
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (code) DO UPDATE SET
            kind = excluded.kind,
            length_m = excluded.length_m,
            width_m = excluded.width_m,
            depth_m = excluded.depth_m,
            flow_gpm = excluded.flow_gpm,
            water_source = excluded.water_source,
            out_of_service = excluded.out_of_service
        """,
        container.code,
        container.kind.value,
        container.length.to("m").amount,
        container.width.to("m").amount,
        container.depth.to("m").amount,
        container.flow.to("gpm").amount,
        container.water_source or None,
        1 if container.out_of_service else 0,
    )
    return container.code


def _container_from(row: sqlite3.Row) -> Container:
    source = row["water_source"]
    return Container(
        code=str(row["code"]),
        kind=ContainerKind(str(row["kind"])),
        length=Quantity(row["length_m"], "m"),
        width=Quantity(row["width_m"], "m"),
        depth=Quantity(row["depth_m"], "m"),
        flow=Quantity(row["flow_gpm"], "gpm"),
        water_source=str(source) if source else "",
        out_of_service=bool(row["out_of_service"]),
    )


def load_container(connection: sqlite3.Connection, code: str) -> Container:
    key = normalise_code(code, field="container")
    row = query_one(connection, "SELECT * FROM container WHERE code = ?", key)
    if row is None:
        raise NotFoundError("container", key)
    return _container_from(row)


def load_containers(connection: sqlite3.Connection) -> ContainerRegister:
    register = ContainerRegister()
    for row in query(connection, "SELECT * FROM container ORDER BY code"):
        register.add(_container_from(row))
    return register


def save_containers(connection: sqlite3.Connection, register: ContainerRegister) -> int:
    for container in register.all():
        save_container(connection, container)
    return len(register)


def delete_container(connection: sqlite3.Connection, code: str) -> bool:
    """Take a container out, which the foreign keys will refuse if it is in use."""

    key = normalise_code(code, field="container")
    return execute(connection, "DELETE FROM container WHERE code = ?", key) == 1


def container_count(connection: sqlite3.Connection) -> int:
    row = query_one(connection, "SELECT COUNT(*) AS n FROM container")
    return int(row["n"]) if row is not None else 0


def total_flow_gpm(connection: sqlite3.Connection) -> Decimal:
    """Every available container's flow, added up in the database rather than in Python."""

    row = query_one(
        connection,
        "SELECT COALESCE(SUM(CAST(flow_gpm AS REAL)), 0) AS total FROM container "
        "WHERE out_of_service = 0",
    )
    return Decimal(str(row["total"])) if row is not None else Decimal(0)
