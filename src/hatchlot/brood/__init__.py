"""Broodstock: the fish the eggs come from, and the paperwork that follows.

`female` is the fish and the checks made on her, `fecundity` is what she is
expected to carry, `eggcount` is how a take is counted, `cross` and `pedigree`
decide what may be mated with what, `screening` decides what the eggs may do,
`take` is the day's record, `register` adds a season up and `shed` plans a day.
"""

from .cross import CrossDesign, CrossPlan, Family, plan_cross
from .eggcount import CountMethod, EggEstimate, reconcile
from .fecundity import DEFAULT_MODEL, FecundityModel, fit
from .female import BroodFemale, CullReason, Ripeness
from .pedigree import Pedigree, effective_population, inbreeding_rate
from .register import BroodRegister, SeasonSummary, summarise_season
from .screening import Assay, AssayLevel, Disposition, Pathogen, Screen, disposition
from .shed import DayPlan, plan_day, ripe_females
from .take import SpawnTake, TakeRegister, TakeState

__all__ = [
    "Assay",
    "AssayLevel",
    "BroodFemale",
    "BroodRegister",
    "CountMethod",
    "CrossDesign",
    "CrossPlan",
    "CullReason",
    "DEFAULT_MODEL",
    "DayPlan",
    "Disposition",
    "EggEstimate",
    "Family",
    "FecundityModel",
    "Pathogen",
    "Pedigree",
    "Ripeness",
    "Screen",
    "SeasonSummary",
    "SpawnTake",
    "TakeRegister",
    "TakeState",
    "disposition",
    "effective_population",
    "fit",
    "inbreeding_rate",
    "plan_cross",
    "plan_day",
    "reconcile",
    "ripe_females",
    "summarise_season",
]
