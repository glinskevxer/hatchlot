"""Planning a day at the spawning shed.

The pieces are all in place by now: who is ripe, how the shed pairs fish, what
the pedigree forbids, and how many eggs the day is supposed to produce. Putting
them together is its own job because the order the checks run in is the whole
value. Pedigree first, because a refused pairing changes which fish are left;
then the design; then the count, because a day that cannot make its number is
still worth running and the manager just needs to know.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import PolicyError, ValidationError
from ..numeric import Number, require_positive
from .cross import CrossDesign, CrossPlan, plan_cross
from .fecundity import DEFAULT_MODEL, FecundityModel
from .female import BroodFemale, Ripeness
from .pedigree import Pedigree
from .register import BroodRegister


@dataclass(frozen=True, slots=True)
class DayPlan:
    """What the shed is going to do today, and what it should produce."""

    cross: CrossPlan
    dams: tuple[BroodFemale, ...]
    expected_eggs: Decimal
    target_eggs: Decimal
    refused_hens: tuple[str, ...]
    refused_pairings: tuple[str, ...]

    @property
    def shortfall(self) -> Decimal:
        gap = self.target_eggs - self.expected_eggs
        return gap if gap > 0 else Decimal(0)

    @property
    def meets_target(self) -> bool:
        return self.expected_eggs >= self.target_eggs

    def line(self) -> str:
        return (
            f"{len(self.dams)} hens, {self.cross.family_count} families, "
            f"{self.expected_eggs:.0f} eggs expected against {self.target_eggs:.0f}"
        )


def ripe_females(register: BroodRegister) -> tuple[BroodFemale, ...]:
    """The hens a crew can work today, biggest first."""

    ripe = register.where(lambda female: female.ripeness is Ripeness.RIPE)
    return tuple(sorted(ripe, key=lambda female: female.weight.to("kg").amount, reverse=True))


def plan_day(
    register: BroodRegister,
    sires: list[str],
    *,
    design: CrossDesign = CrossDesign.FACTORIAL,
    pedigree: Pedigree | None = None,
    target_eggs: Number = 10000,
    model: FecundityModel | None = None,
    max_sire_share: Number = "0.5",
) -> DayPlan:
    """Work out today's crosses, dropping the pairings the pedigree forbids."""

    target = require_positive(target_eggs, field="target_eggs")
    hens = ripe_females(register)
    if not hens:
        raise ValidationError("nothing is ripe today", field="register")
    if not sires:
        raise ValidationError("no males to spawn against", field="sires")
    tree = pedigree or Pedigree()
    usable: list[BroodFemale] = []
    refused: list[str] = []
    for hen in hens:
        blocked = []
        for sire in sires:
            try:
                tree.check_mating(hen.tag, sire)
            except PolicyError:
                blocked.append(sire)
        if len(blocked) == len(sires):
            refused.append(hen.tag)
        else:
            usable.append(hen)
    if not usable:
        raise PolicyError("every ripe hen is too close to every male", rule="shed.no_pairings")
    if design is CrossDesign.PAIRWISE:
        pairs = min(len(usable), len(sires))
        usable = usable[:pairs]
        sires = sires[:pairs]
    cross = plan_cross(
        design,
        [hen.tag for hen in usable],
        sires,
        max_sire_share=max_sire_share,
    )
    kept = []
    refused_pairings = []
    for family in cross.families:
        try:
            tree.check_mating(family.dam, family.sire)
        except PolicyError:
            refused_pairings.append(family.identifier)
        else:
            kept.append(family)
    cross = CrossPlan(
        design=cross.design,
        families=tuple(kept),
        dams=cross.dams,
        sires=cross.sires,
    )
    curve = model or DEFAULT_MODEL
    expected = curve.expected_total([hen.length for hen in usable])
    return DayPlan(
        cross=cross,
        dams=tuple(usable),
        expected_eggs=expected,
        target_eggs=target,
        refused_hens=tuple(refused),
        refused_pairings=tuple(refused_pairings),
    )
