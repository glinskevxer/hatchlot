"""The database connection, and the settings that have to be on it.

SQLite will happily run without foreign keys enforced, in a journal mode that
loses the last transaction on a power cut, and with a busy timeout of zero so a
second process fails instantly. None of those defaults suit a station where the
hatchery manager and a report script are both on the file at once, so the
connection is opened here and nowhere else.

Decimal is the other reason this module exists. SQLite has no decimal type, so
everything numeric is stored as text and converted at the boundary. A float
column would round a fish count.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..errors import HatchlotError, ValidationError

MEMORY = ":memory:"


class StoreError(HatchlotError):
    """The database refused something."""


def _adapt_decimal(value: Decimal) -> str:
    return str(value)


def _convert_decimal(raw: bytes) -> Decimal:
    try:
        return Decimal(raw.decode("utf-8"))
    except (InvalidOperation, UnicodeDecodeError):
        raise ValidationError(f"{raw!r} is not a stored number", field="value") from None


sqlite3.register_adapter(Decimal, _adapt_decimal)
sqlite3.register_converter("DECIMAL", _convert_decimal)


@dataclass(frozen=True, slots=True)
class Settings:
    """How the connection is opened."""

    path: str = MEMORY
    timeout_seconds: float = 5.0
    foreign_keys: bool = True
    journal_mode: str = "WAL"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValidationError("a timeout has to be positive", field="timeout_seconds")
        if self.journal_mode.upper() not in {"WAL", "DELETE", "TRUNCATE", "MEMORY"}:
            raise ValidationError(
                f"{self.journal_mode!r} is not a journal mode", field="journal_mode"
            )

    @property
    def is_memory(self) -> bool:
        return self.path == MEMORY


def connect(settings: Settings | None = None) -> sqlite3.Connection:
    """Open a connection with the settings a station needs."""

    config = settings or Settings()
    if not config.is_memory:
        parent = Path(config.path).expanduser().parent
        if parent and not parent.exists():
            raise ValidationError(f"no directory at {parent}", field="path")
    connection = sqlite3.connect(
        config.path,
        timeout=config.timeout_seconds,
        detect_types=sqlite3.PARSE_DECLTYPES,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    if config.foreign_keys:
        connection.execute("PRAGMA foreign_keys = ON")
    if not config.is_memory:
        connection.execute(f"PRAGMA journal_mode = {config.journal_mode}")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block in one transaction, rolled back on anything raised.

    Nested use is refused rather than silently flattened, because a caller who
    thinks they have an inner transaction and does not is a caller whose rollback
    does nothing.
    """

    if connection.in_transaction:
        raise StoreError("a transaction is already open on this connection")
    connection.execute("BEGIN")
    try:
        yield connection
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def query(connection: sqlite3.Connection, sql: str, *params: Any) -> list[sqlite3.Row]:
    """Run a select and hand back the rows."""

    return list(connection.execute(sql, params))


def query_one(connection: sqlite3.Connection, sql: str, *params: Any) -> sqlite3.Row | None:
    rows = query(connection, sql, *params)
    if len(rows) > 1:
        raise StoreError(f"expected one row, got {len(rows)}")
    return rows[0] if rows else None


def execute(connection: sqlite3.Connection, sql: str, *params: Any) -> int:
    """Run a statement and hand back how many rows it touched."""

    try:
        cursor = connection.execute(sql, params)
    except sqlite3.IntegrityError as error:
        raise StoreError(str(error)) from None
    return cursor.rowcount


def table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = query(
        connection,
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name",
    )
    return tuple(str(row["name"]) for row in rows)


def column_names(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    if table not in table_names(connection):
        raise ValidationError(f"no table called {table!r}", field="table")
    rows = query(connection, f"PRAGMA table_info({table})")
    return tuple(str(row["name"]) for row in rows)


def foreign_keys_on(connection: sqlite3.Connection) -> bool:
    row = query_one(connection, "PRAGMA foreign_keys")
    return bool(row[0]) if row is not None else False
