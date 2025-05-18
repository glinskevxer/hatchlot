"""The station's schema, as a list of migrations that never change.

Every table here is keyed by the code a person writes on a form, because that is
the key the paperwork uses and a surrogate integer id would mean every report
join had to go through a lookup nobody reading the SQL would expect.

Numbers are stored as text in DECIMAL columns and dates as ISO text. SQLite has
neither type; what it has is a converter, and the converter is registered in
`db`. Anything that stores a float here will one day report a fish count of
9499.999999.
"""

from __future__ import annotations

from .migrations import Migration

CONTAINERS = Migration(
    version=1,
    name="containers and water sources",
    statements=(
        """
        CREATE TABLE water_source (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            design_flow_gpm DECIMAL NOT NULL,
            minimum_flow_gpm DECIMAL
        )
        """,
        """
        CREATE TABLE container (
            code TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            length_m DECIMAL NOT NULL,
            width_m DECIMAL NOT NULL,
            depth_m DECIMAL NOT NULL,
            flow_gpm DECIMAL NOT NULL,
            water_source TEXT REFERENCES water_source (code),
            out_of_service INTEGER NOT NULL DEFAULT 0
        )
        """,
        "CREATE INDEX container_source ON container (water_source)",
    ),
)

LOTS = Migration(
    version=2,
    name="rearing lots",
    statements=(
        """
        CREATE TABLE rearing_lot (
            code TEXT PRIMARY KEY,
            container TEXT NOT NULL REFERENCES container (code),
            species TEXT NOT NULL,
            ponded_on TEXT NOT NULL,
            population DECIMAL NOT NULL,
            mean_weight_g DECIMAL NOT NULL,
            state TEXT NOT NULL,
            origin_egg_lot TEXT
        )
        """,
        "CREATE INDEX rearing_lot_container ON rearing_lot (container)",
        "CREATE INDEX rearing_lot_state ON rearing_lot (state)",
    ),
)

LEDGER = Migration(
    version=3,
    name="the movement ledger",
    statements=(
        """
        CREATE TABLE ledger_entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            lot TEXT NOT NULL,
            kind TEXT NOT NULL,
            count DECIMAL NOT NULL,
            entered_by TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            counterparty TEXT NOT NULL DEFAULT ''
        )
        """,
        "CREATE INDEX ledger_entry_lot ON ledger_entry (lot, day)",
    ),
)

READINGS = Migration(
    version=4,
    name="water readings",
    statements=(
        """
        CREATE TABLE water_reading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            taken_at TEXT NOT NULL,
            container TEXT NOT NULL,
            celsius DECIMAL NOT NULL,
            oxygen_mgl DECIMAL NOT NULL,
            UNIQUE (taken_at, container)
        )
        """,
        "CREATE INDEX water_reading_container ON water_reading (container, taken_at)",
    ),
)

FEEDING = Migration(
    version=5,
    name="feeding and mortality",
    statements=(
        """
        CREATE TABLE feeding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            lot TEXT NOT NULL,
            feed_lot TEXT NOT NULL,
            amount_kg DECIMAL NOT NULL,
            method TEXT NOT NULL,
            fed_by TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE mortality (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            lot TEXT NOT NULL,
            count DECIMAL NOT NULL,
            cause TEXT NOT NULL,
            recorded_by TEXT NOT NULL
        )
        """,
        "CREATE INDEX feeding_lot ON feeding (lot, day)",
        "CREATE INDEX mortality_lot ON mortality (lot, day)",
    ),
)

STATION = Migration(
    version=6,
    name="station profile",
    statements=(
        """
        CREATE TABLE station (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system TEXT NOT NULL,
            brood_start_month INTEGER NOT NULL,
            elevation_m DECIMAL NOT NULL,
            loading_tolerance DECIMAL NOT NULL,
            inventory_tolerance DECIMAL NOT NULL,
            mortality_alert DECIMAL NOT NULL,
            report_places INTEGER NOT NULL
        )
        """,
    ),
)

ALL: list[Migration] = [CONTAINERS, LOTS, LEDGER, READINGS, FEEDING, STATION]


def latest_version() -> int:
    """The version a fully migrated database sits at."""

    return max(migration.version for migration in ALL)


def migration_named(name: str) -> Migration:
    """Find a migration by name, for a report that has to explain itself."""

    from ..errors import ValidationError

    for migration in ALL:
        if migration.name == name:
            return migration
    raise ValidationError(f"no migration called {name!r}", field="name")
