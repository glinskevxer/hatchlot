"""Distribution: getting the fish onto a truck and into somebody else's water.

`request` is what was asked for, `allocation` matches it against what exists,
`haul` sizes the truck, `release` runs the gates and keeps the record, and
`summary` reads the season off both sides at once.
"""

from .allocation import AllocationPlan, AllocationPolicy, Offer, allocate
from .haul import HaulLoad, OxygenSupply, Tank, haul_density, tempering_minutes
from .release import Release, ReleaseKind, ReleaseRegister, release_fish
from .request import RequestBook, RequestState, StockingRequest
from .summary import DistributionSummary, by_water, summarise_distribution

__all__ = [
    "AllocationPlan",
    "AllocationPolicy",
    "DistributionSummary",
    "HaulLoad",
    "Offer",
    "OxygenSupply",
    "Release",
    "ReleaseKind",
    "ReleaseRegister",
    "RequestBook",
    "RequestState",
    "StockingRequest",
    "Tank",
    "allocate",
    "by_water",
    "haul_density",
    "release_fish",
    "summarise_distribution",
    "tempering_minutes",
]
