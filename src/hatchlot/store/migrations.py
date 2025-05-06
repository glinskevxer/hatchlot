"""Migrations, and the checksum that stops one being edited after it has run.

The rule is simple and it is the whole module. A migration that has been applied
is frozen. If its text changes afterwards, every database that already ran it is
now different from every database that runs it fresh, and nothing in either of
them will say so. So the checksum of each applied migration is stored, and a
mismatch is an error rather than a warning.

Migrations run in order, in one transaction each, and the record of what ran is
written in the same transaction as the change itself.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from ..errors import ValidationError
from .db import StoreError, execute, query, query_one, table_names, transaction

LEDGER_TABLE = "schema_migration"


@dataclass(frozen=True, slots=True)
class Migration:
    """One numbered change to the schema."""

    version: int
    name: str
    statements: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValidationError("migrations are numbered from one", field="version")
        if not self.name.strip():
            raise ValidationError("a migration needs a name", field="name")
        object.__setattr__(self, "name", self.name.strip())
        if not self.statements:
            raise ValidationError("a migration does something", field="statements")
        for statement in self.statements:
            if not statement.strip():
                raise ValidationError("an empty statement", field="statements")

    @property
    def checksum(self) -> str:
        joined = "\n".join(statement.strip() for statement in self.statements)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def ensure_ledger(connection: sqlite3.Connection) -> None:
    """Make the table that records what has been applied."""

    if LEDGER_TABLE in table_names(connection):
        return
    execute(
        connection,
        f"""
        CREATE TABLE {LEDGER_TABLE} (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """,
    )


def applied(connection: sqlite3.Connection) -> dict[int, str]:
    """Which versions have run, and what their text hashed to."""

    ensure_ledger(connection)
    rows = query(connection, f"SELECT version, checksum FROM {LEDGER_TABLE} ORDER BY version")
    return {int(row["version"]): str(row["checksum"]) for row in rows}


def current_version(connection: sqlite3.Connection) -> int:
    """The highest version applied, or zero on a fresh database."""

    done = applied(connection)
    return max(done) if done else 0


def check_order(migrations: list[Migration]) -> None:
    """Refuse a set with a repeated or out of order version in it."""

    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise ValidationError("two migrations share a version", field="migrations")
    if versions != sorted(versions):
        raise ValidationError("the migrations are out of order", field="migrations")


def check_integrity(connection: sqlite3.Connection, migrations: list[Migration]) -> None:
    """Refuse a migration whose text has changed since it was applied."""

    done = applied(connection)
    for migration in migrations:
        recorded = done.get(migration.version)
        if recorded is None:
            continue
        if recorded != migration.checksum:
            raise StoreError(
                f"migration {migration.version} ({migration.name}) has changed since it was applied"
            )


def pending(connection: sqlite3.Connection, migrations: list[Migration]) -> tuple[Migration, ...]:
    """The migrations that have not run yet, in order."""

    check_order(migrations)
    check_integrity(connection, migrations)
    done = applied(connection)
    return tuple(migration for migration in migrations if migration.version not in done)


def apply(connection: sqlite3.Connection, migration: Migration) -> int:
    """Run one migration and record it, both in the same transaction."""

    ensure_ledger(connection)
    with transaction(connection):
        for statement in migration.statements:
            connection.execute(statement)
        execute(
            connection,
            f"INSERT INTO {LEDGER_TABLE} (version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
            migration.version,
            migration.name,
            migration.checksum,
            datetime.now(UTC).isoformat(timespec="seconds"),
        )
    return migration.version


def migrate(connection: sqlite3.Connection, migrations: list[Migration]) -> tuple[int, ...]:
    """Bring a database up to date, and say what ran."""

    ran: list[int] = []
    for migration in pending(connection, migrations):
        ran.append(apply(connection, migration))
    return tuple(ran)


def is_up_to_date(connection: sqlite3.Connection, migrations: list[Migration]) -> bool:
    return not pending(connection, migrations)


def history(connection: sqlite3.Connection) -> tuple[tuple[int, str, str], ...]:
    """What ran, when, in the order it ran."""

    ensure_ledger(connection)
    rows = query(
        connection,
        f"SELECT version, name, applied_at FROM {LEDGER_TABLE} ORDER BY version",
    )
    return tuple((int(row["version"]), str(row["name"]), str(row["applied_at"])) for row in rows)


def applied_at(connection: sqlite3.Connection, version: int) -> str | None:
    ensure_ledger(connection)
    row = query_one(connection, f"SELECT applied_at FROM {LEDGER_TABLE} WHERE version = ?", version)
    return str(row["applied_at"]) if row is not None else None
