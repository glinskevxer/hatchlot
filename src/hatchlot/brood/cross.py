"""Mating designs, and the families that come out of them.

Which male fertilises which female is a genetics decision with a paper trail. A
one to one pairing keeps families separate and traceable. A factorial design
crosses every female in a block against every male in it, which spreads the
contribution of any one parent. Pooled milt is quick and cheap and destroys the
pedigree, so it is allowed and it is recorded as what it is.

The rules that bite are the reuse limits: no male should sire more than his
share of a year class, and a design that breaks that is refused before the crew
starts rather than found in a report in March.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import DuplicateError, PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive


class CrossDesign(Enum):
    """How the shed is pairing fish today."""

    PAIRWISE = "pairwise"
    FACTORIAL = "factorial"
    POOLED = "pooled"

    @property
    def keeps_pedigree(self) -> bool:
        return self is not CrossDesign.POOLED


@dataclass(frozen=True, slots=True, order=True)
class Family:
    """One cross: a dam, a sire, and the identity the offspring inherit."""

    dam: str
    sire: str

    def __init__(self, dam: str, sire: str) -> None:
        object.__setattr__(self, "dam", normalise_code(dam, field="dam"))
        object.__setattr__(self, "sire", normalise_code(sire, field="sire"))
        if self.dam == self.sire:
            raise ValidationError("a fish cannot be crossed with itself", field="sire")

    @property
    def identifier(self) -> str:
        return f"{self.dam}x{self.sire}"


@dataclass(frozen=True, slots=True)
class CrossPlan:
    """A design worked out into the families it produces."""

    design: CrossDesign
    families: tuple[Family, ...]
    dams: tuple[str, ...]
    sires: tuple[str, ...]

    @property
    def family_count(self) -> int:
        return len(self.families)

    def sire_load(self) -> dict[str, int]:
        """How many families each male ends up in."""

        counts: dict[str, int] = {sire: 0 for sire in self.sires}
        for family in self.families:
            counts[family.sire] += 1
        return counts

    def dam_load(self) -> dict[str, int]:
        counts: dict[str, int] = {dam: 0 for dam in self.dams}
        for family in self.families:
            counts[family.dam] += 1
        return counts

    def busiest_sire_share(self) -> Decimal:
        """The share of families the hardest worked male is in."""

        if not self.families:
            return Decimal(0)
        return Decimal(max(self.sire_load().values())) / Decimal(self.family_count)

    def families_of(self, tag: str) -> tuple[Family, ...]:
        code = normalise_code(tag, field="tag")
        return tuple(family for family in self.families if code in (family.dam, family.sire))


def _clean(tags: list[str], *, field: str) -> tuple[str, ...]:
    if not tags:
        raise ValidationError(f"no {field} to cross", field=field)
    cleaned = [normalise_code(tag, field=field) for tag in tags]
    seen: set[str] = set()
    for tag in cleaned:
        if tag in seen:
            raise DuplicateError(field, tag)
        seen.add(tag)
    return tuple(cleaned)


def plan_cross(
    design: CrossDesign,
    dams: list[str],
    sires: list[str],
    *,
    max_sire_share: Number = "0.5",
) -> CrossPlan:
    """Work a design into families, refusing one that leans on a single male."""

    if not isinstance(design, CrossDesign):
        raise ValidationError(f"{design!r} is not a cross design", field="design")
    dam_tags = _clean(dams, field="dam")
    sire_tags = _clean(sires, field="sire")
    overlap = set(dam_tags) & set(sire_tags)
    if overlap:
        raise ValidationError(f"{sorted(overlap)[0]} is on both sides of the cross", field="sires")
    if design is CrossDesign.PAIRWISE:
        if len(dam_tags) != len(sire_tags):
            raise ValidationError("a pairwise cross needs one male for every female", field="sires")
        families = tuple(Family(dam, sire) for dam, sire in zip(dam_tags, sire_tags, strict=True))
    elif design is CrossDesign.FACTORIAL:
        families = tuple(Family(dam, sire) for dam in dam_tags for sire in sire_tags)
    else:
        families = tuple(Family(dam, "POOLED-" + sire_tags[0]) for dam in dam_tags)
    plan = CrossPlan(design=design, families=families, dams=dam_tags, sires=sire_tags)
    ceiling = require_positive(max_sire_share, field="max_sire_share")
    # A block of one family is a hundred percent of itself, which is not the
    # thing the rule is about. Judge it once the block has something to spread.
    judged = design.keeps_pedigree and plan.family_count > 1
    if judged and plan.busiest_sire_share() > ceiling:
        raise PolicyError(
            f"one male would sire {plan.busiest_sire_share():.0%} of the families",
            rule="cross.sire_share",
        )
    return plan


def merge_plans(plans: list[CrossPlan]) -> CrossPlan:
    """Put a day's blocks together into one plan for the take.

    Factorial blocks are how a shed actually works: four hens against four bucks
    at a time, repeated. The merged plan is what the sire share should really be
    judged on, and judging each block alone is how a male quietly ends up in a
    third of a year class.
    """

    if not plans:
        raise ValidationError("no blocks to merge", field="plans")
    designs = {plan.design for plan in plans}
    if len(designs) != 1:
        raise ValidationError("cannot merge blocks of different designs", field="plans")
    families: list[Family] = []
    dams: list[str] = []
    sires: list[str] = []
    for plan in plans:
        families.extend(plan.families)
        dams.extend(plan.dams)
        sires.extend(plan.sires)
    if len(set(families)) != len(families):
        raise ValidationError("two blocks make the same family", field="plans")
    return CrossPlan(
        design=plans[0].design,
        families=tuple(families),
        dams=tuple(dict.fromkeys(dams)),
        sires=tuple(dict.fromkeys(sires)),
    )
