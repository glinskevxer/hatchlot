"""Production accounting for a coldwater salmonid hatchery.

The package is split the way the station is: `water` for the supply and what is
dissolved in it, `brood` for the fish the eggs come from, `incubation` for the
eggs, `rearing` for the fish, `growth`, `feed`, `health`, `marking`,
`distribution` and `permits` for what happens to them, and `store`, `ingest`,
`reporting` and `cli` for the machinery around all of it.

What is exported here is the handful of things nearly every caller needs: the
error hierarchy so a caller can catch what this package raises on purpose, the
quantity types, and the station profile.
"""

from .calendar import DateRange
from .errors import (
    ConversionError,
    DuplicateError,
    HatchlotError,
    NotFoundError,
    PolicyError,
    StateError,
    UnitError,
    ValidationError,
)
from .identifiers import LotCode
from .quantities.base import Quantity
from .quantities.temperature import Temperature, TemperatureSpan
from .species import Species, resolve_species, species
from .station import StationProfile
from .units import Dimension, System, convert

__version__ = "0.1.0"

__all__ = [
    "ConversionError",
    "DateRange",
    "Dimension",
    "DuplicateError",
    "HatchlotError",
    "LotCode",
    "NotFoundError",
    "PolicyError",
    "Quantity",
    "Species",
    "StateError",
    "StationProfile",
    "System",
    "Temperature",
    "TemperatureSpan",
    "UnitError",
    "ValidationError",
    "__version__",
    "convert",
    "resolve_species",
    "species",
]
