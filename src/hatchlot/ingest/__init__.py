"""Ingest: getting other people's files into the station's own numbers.

`profile` says what a vendor's columns mean, `reader` turns a file into rows and
quarantines the ones that will not read, `dedupe` keeps a resent file from being
imported twice, and `pipeline` runs the three of them in order.
"""

from .dedupe import ImportLedger, dedupe, file_hash, row_key
from .pipeline import ImportReport, import_rate, run_import, run_with_profiles
from .profile import ColumnMap, FieldKind, Profile, choose_profile
from .reader import ReadResult, Rejected, read_file, read_rows

__all__ = [
    "ColumnMap",
    "FieldKind",
    "ImportLedger",
    "ImportReport",
    "Profile",
    "ReadResult",
    "Rejected",
    "choose_profile",
    "dedupe",
    "file_hash",
    "import_rate",
    "read_file",
    "read_rows",
    "row_key",
    "run_import",
    "run_with_profiles",
]
