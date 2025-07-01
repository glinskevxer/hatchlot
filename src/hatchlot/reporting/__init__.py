"""Reporting: turning the registers into something a person reads.

`tables` prints, `lot_history` follows one lot through every register,
`production` is the monthly report, `compliance` is what an auditor would ask
for, and `export` hands the same rows to a spreadsheet.
"""

from .compliance import Area, ComplianceReport, build_compliance_report, render_compliance
from .export import to_csv, to_records, write_csv
from .lot_history import LotHistory, build_history, render_history, timeline
from .production import ProductionReport, build_production_report, render_production
from .tables import Align, Column, heading, render_pairs, render_table

__all__ = [
    "Align",
    "Area",
    "Column",
    "ComplianceReport",
    "LotHistory",
    "ProductionReport",
    "build_compliance_report",
    "build_history",
    "build_production_report",
    "heading",
    "render_compliance",
    "render_history",
    "render_pairs",
    "render_production",
    "render_table",
    "timeline",
    "to_csv",
    "to_records",
    "write_csv",
]
