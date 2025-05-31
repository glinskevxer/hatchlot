"""Lots and the ledger, stored and loaded.

The ledger is append only in the database as well as in the engine. There is no
update and no delete on `ledger_entry`, and an entry that turns out to be wrong
is corrected with an adjustment entry rather than by editing the past. That is
the whole reason the table exists, so the repository does not offer a way round
it.

Loading a lot's population is deliberately not done by summing the ledger. The
lot carries its own number and the ledger is the check on it, and if this module
rebuilt one from the other there would be nothing left to reconcile.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import NotFoundError, ValidationError
from ..identifiers import LotCode, normalise_code
from ..quantities.base import Quantity
from ..rearing.ledger import EntryKind, Ledger, LedgerEntry
from ..rearing.lot import LotState, RearingLot
from .db import execute, query, query_one


def save_lot(connection: sqlite3.Connection, lot: RearingLot) -> str:
    """Write a rearing lot, replacing whatever was under that code."""

    execute(
        connection,
        """
        INSERT INTO rearing_lot (
            code, container, species, ponded_on, population, mean_weight_g, state,
            origin_egg_lot
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (code) DO UPDATE SET
            container = excluded.container,
            species = excluded.species,
            ponded_on = excluded.ponded_on,
            population = excluded.population,
            mean_weight_g = excluded.mean_weight_g,
            state = excluded.state,
            origin_egg_lot = excluded.origin_egg_lot
        """,
        str(lot.code),
        lot.container,
        lot.code.species,
        lot.ponded_on.isoformat(),
        lot.population,
        lot.mean_weight.to("g").amount,
        lot.state.value,
        lot.origin_egg_lot or None,
    )
    return str(lot.code)


def _lot_from(row: sqlite3.Row) -> RearingLot:
    origin = row["origin_egg_lot"]
    return RearingLot(
        code=LotCode.parse(str(row["code"])),
        container=str(row["container"]),
        ponded_on=parse_date(str(row["ponded_on"])),
        population=Decimal(str(row["population"])),
        mean_weight=Quantity(row["mean_weight_g"], "g"),
        state=LotState(str(row["state"])),
        origin_egg_lot=str(origin) if origin else "",
    )


def load_lot(connection: sqlite3.Connection, code: str) -> RearingLot:
    key = normalise_code(code, field="lot")
    row = query_one(connection, "SELECT * FROM rearing_lot WHERE code = ?", key)
    if row is None:
        raise NotFoundError("rearing lot", key)
    return _lot_from(row)


def load_lots(
    connection: sqlite3.Connection, *, container: str | None = None, live_only: bool = False
) -> tuple[RearingLot, ...]:
    """Every lot, optionally narrowed to one unit or to the live ones."""

    sql = "SELECT * FROM rearing_lot"
    clauses: list[str] = []
    params: list[object] = []
    if container is not None:
        clauses.append("container = ?")
        params.append(normalise_code(container, field="container"))
    if live_only:
        closed = [state.value for state in LotState if state.is_closed]
        clauses.append(f"state NOT IN ({', '.join('?' for _ in closed)})")
        params.extend(closed)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY code"
    return tuple(_lot_from(row) for row in query(connection, sql, *params))


def save_entry(connection: sqlite3.Connection, entry: LedgerEntry) -> int:
    """Append one ledger entry. There is no update and no delete."""

    execute(
        connection,
        """
        INSERT INTO ledger_entry (day, lot, kind, count, entered_by, reason, counterparty)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        entry.day.isoformat(),
        entry.lot,
        entry.kind.value,
        entry.count,
        entry.entered_by,
        entry.reason,
        entry.counterparty,
    )
    row = query_one(connection, "SELECT last_insert_rowid() AS id")
    return int(row["id"]) if row is not None else 0


def _entry_from(row: sqlite3.Row) -> LedgerEntry:
    return LedgerEntry(
        day=parse_date(str(row["day"])),
        lot=str(row["lot"]),
        kind=EntryKind(str(row["kind"])),
        count=Decimal(str(row["count"])),
        entered_by=str(row["entered_by"]),
        reason=str(row["reason"]),
        counterparty=str(row["counterparty"]),
    )


def load_ledger(
    connection: sqlite3.Connection, *, lot: str | None = None, window: DateRange | None = None
) -> Ledger:
    """Rebuild the ledger, optionally for one lot or one window."""

    sql = "SELECT * FROM ledger_entry"
    clauses: list[str] = []
    params: list[object] = []
    if lot is not None:
        clauses.append("lot = ?")
        params.append(normalise_code(lot, field="lot"))
    if window is not None:
        clauses.append("day BETWEEN ? AND ?")
        params.extend([window.start.isoformat(), window.end.isoformat()])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY day, id"
    book = Ledger()
    for row in query(connection, sql, *params):
        book.record(_entry_from(row))
    return book


def save_ledger(connection: sqlite3.Connection, ledger: Ledger) -> int:
    """Append every entry in a ledger, refusing to write it twice.

    The guard is crude on purpose: a ledger whose entries are already in the
    database would double every count if it were appended again, and there is no
    version of that mistake that is not a disaster.
    """

    existing = query_one(connection, "SELECT COUNT(*) AS n FROM ledger_entry")
    if existing is not None and int(existing["n"]) and len(ledger):
        held = load_ledger(connection)
        if len(held) == len(ledger):
            raise ValidationError("that ledger looks like it is already stored", field="ledger")
    for entry in ledger.all():
        save_entry(connection, entry)
    return len(ledger)


def lot_population(connection: sqlite3.Connection, code: str) -> Decimal:
    """The population the lot record carries, which is not the ledger's answer."""

    return load_lot(connection, code).population


def ledger_balance(connection: sqlite3.Connection, code: str) -> Decimal:
    """The population the ledger rebuilds, which is the check on the lot record."""

    return load_ledger(connection, lot=code).balance(code).closing
