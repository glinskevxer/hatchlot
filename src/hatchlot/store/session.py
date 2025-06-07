"""A session: one open database, migrated, with the station's profile on it.

Everything above this point takes a connection. This is the one place that
decides where the file is, brings the schema up to date, and hands out the
station profile that half the rules need. A caller that wants the whole station
opens a session; a caller that wants one query still takes a connection.

Closing is explicit and the session is also a context manager, because a station
that leaves connections open on a WAL database will eventually wonder why its
backup is three files.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from types import TracebackType

from ..errors import NotFoundError, ValidationError
from ..rearing.container import ContainerRegister
from ..rearing.ledger import Ledger
from ..rearing.lot import RearingLot
from ..station import StationProfile
from ..units import System
from ..water.source import SourceRegister
from .db import Settings, connect, execute, query_one, transaction
from .lots import load_ledger, load_lots, save_lot
from .migrations import current_version, migrate
from .repositories import load_containers, load_sources, save_container, save_source
from .schema import ALL, latest_version


@dataclass
class Session:
    """One open station database."""

    connection: sqlite3.Connection
    settings: Settings

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def version(self) -> int:
        return current_version(self.connection)

    @property
    def is_current(self) -> bool:
        return self.version == latest_version()

    def containers(self) -> ContainerRegister:
        return load_containers(self.connection)

    def sources(self) -> SourceRegister:
        return load_sources(self.connection)

    def lots(self, *, live_only: bool = True) -> tuple[RearingLot, ...]:
        return load_lots(self.connection, live_only=live_only)

    def ledger(self, *, lot: str | None = None) -> Ledger:
        return load_ledger(self.connection, lot=lot)

    def save_profile(self, profile: StationProfile) -> str:
        """Write the station profile, of which there is one."""

        execute(
            self.connection,
            """
            INSERT INTO station (
                code, name, system, brood_start_month, elevation_m, loading_tolerance,
                inventory_tolerance, mortality_alert, report_places
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (code) DO UPDATE SET
                name = excluded.name,
                system = excluded.system,
                brood_start_month = excluded.brood_start_month,
                elevation_m = excluded.elevation_m,
                loading_tolerance = excluded.loading_tolerance,
                inventory_tolerance = excluded.inventory_tolerance,
                mortality_alert = excluded.mortality_alert,
                report_places = excluded.report_places
            """,
            profile.code,
            profile.name,
            profile.system.value,
            profile.brood_start_month,
            profile.elevation_m,
            profile.loading_tolerance,
            profile.inventory_tolerance,
            profile.mortality_alert,
            profile.report_places,
        )
        return profile.code

    def profile(self, code: str | None = None) -> StationProfile:
        """Load the station profile, refusing an ambiguous answer."""

        if code is None:
            row = query_one(self.connection, "SELECT COUNT(*) AS n FROM station")
            held = int(row["n"]) if row is not None else 0
            if held == 0:
                raise NotFoundError("station", "any")
            if held > 1:
                raise ValidationError(
                    "more than one station profile is stored, name the one you want",
                    field="code",
                )
            found = query_one(self.connection, "SELECT * FROM station")
        else:
            found = query_one(self.connection, "SELECT * FROM station WHERE code = ?", code)
        if found is None:
            raise NotFoundError("station", code or "any")
        return StationProfile(
            code=str(found["code"]),
            name=str(found["name"]),
            system=System(str(found["system"])),
            brood_start_month=int(found["brood_start_month"]),
            elevation_m=Decimal(str(found["elevation_m"])),
            loading_tolerance=Decimal(str(found["loading_tolerance"])),
            inventory_tolerance=Decimal(str(found["inventory_tolerance"])),
            mortality_alert=Decimal(str(found["mortality_alert"])),
            report_places=int(found["report_places"]),
        )

    def save_station(
        self, sources: SourceRegister, containers: ContainerRegister
    ) -> tuple[int, int]:
        """Write the water and the units in one transaction, in that order."""

        with transaction(self.connection):
            for source in sources.all():
                save_source(self.connection, source)
            for container in containers.all():
                save_container(self.connection, container)
        return len(sources), len(containers)

    def save_lots(self, lots: list[RearingLot]) -> int:
        with transaction(self.connection):
            for lot in lots:
                save_lot(self.connection, lot)
        return len(lots)


def open_session(path: str = ":memory:", *, migrate_to_latest: bool = True) -> Session:
    """Open a station database and bring its schema up to date."""

    settings = Settings(path=path)
    connection = connect(settings)
    if migrate_to_latest:
        migrate(connection, ALL)
    return Session(connection=connection, settings=settings)


@contextmanager
def session(path: str = ":memory:") -> Iterator[Session]:
    """Open a session, and close it whatever happens."""

    opened = open_session(path)
    try:
        yield opened
    finally:
        opened.close()
