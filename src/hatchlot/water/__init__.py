"""Water: where it comes from, what is dissolved in it, and how much it carries.

The modules underneath split along the lines a hatchery does. `source` is the
supply and its blends, `oxygen` and `gas` are what is dissolved in it, `quality`
is the rest of the chemistry, `thermal` is the clock incubation runs on,
`capacity` is what the water will carry, `budget` divides it when it is short,
and `monitoring` and `summary` are what the meters said.
"""

from .capacity import BindingLimit, Capacity, carrying_capacity
from .gas import GasReading, GasRisk
from .monitoring import Excursion, ExcursionKind, MonitoringLog, Reading, Thresholds
from .oxygen import percent_saturation, saturation_concentration
from .quality import QualityFlag, QualityLimits, WaterQuality
from .source import SourceKind, SourceRegister, WaterSource
from .summary import SupplyState, WaterSummary, summarise
from .thermal import GapPolicy, ThermalSeries

__all__ = [
    "BindingLimit",
    "Capacity",
    "Excursion",
    "ExcursionKind",
    "GapPolicy",
    "GasReading",
    "GasRisk",
    "MonitoringLog",
    "QualityFlag",
    "QualityLimits",
    "Reading",
    "SourceKind",
    "SourceRegister",
    "SupplyState",
    "ThermalSeries",
    "Thresholds",
    "WaterQuality",
    "WaterSource",
    "WaterSummary",
    "carrying_capacity",
    "percent_saturation",
    "saturation_concentration",
    "summarise",
]
