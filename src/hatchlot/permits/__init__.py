"""Permits: what the station is allowed to discharge, and what it did discharge.

`limits` is what the permit says, `monitoring` is what the samples said,
`permit` holds the two together and builds the period report, and `effluent`
estimates the discharge off the feed before anybody takes a sample.
"""

from .effluent import Loading, estimate_loading, feed_ceiling, projected_against
from .limits import Basis, Limit, Parameter, Sample, exceeds, share_of_limit
from .monitoring import Exceedance, MonitoringRecord, Reading
from .permit import LimitResult, PeriodReport, Permit, build_report, periods

__all__ = [
    "Basis",
    "Exceedance",
    "Limit",
    "LimitResult",
    "Loading",
    "MonitoringRecord",
    "Parameter",
    "PeriodReport",
    "Permit",
    "Reading",
    "Sample",
    "build_report",
    "estimate_loading",
    "exceeds",
    "feed_ceiling",
    "periods",
    "projected_against",
    "share_of_limit",
]
