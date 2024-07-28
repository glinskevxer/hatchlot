"""Effective population size, and the matings a pedigree forbids.

A hatchery can hold a run's numbers up for years and still lose it, because the
number that matters is not how many fish were spawned but how evenly they
contributed. Ten females against one male is twenty parents on paper and an
effective population of under four.

Two numbers do the work. The effective population size, which sex ratio and
uneven family sizes both pull down, and the rate of inbreeding per generation
that falls out of it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide, to_decimal
from .cross import Family


def effective_population(males: int, females: int) -> Decimal:
    """The classic sex ratio formula: four times the product over the sum."""

    if males <= 0 or females <= 0:
        raise ValidationError("both sexes have to be represented", field="parents")
    return Decimal(4 * males * females) / Decimal(males + females)


def inbreeding_rate(effective_size: Number) -> Decimal:
    """The rise in inbreeding per generation at an effective size."""

    size = require_positive(effective_size, field="effective_size")
    return Decimal(1) / (Decimal(2) * size)


def variance_effective_population(family_sizes: list[int]) -> Decimal:
    """Effective size allowing for how unevenly the families contributed.

    Two families of five hundred is not the same as one of nine hundred and one
    of a hundred, and this is the number that says so.
    """

    if len(family_sizes) < 2:
        raise ValidationError("a variance needs at least two families", field="family_sizes")
    sizes = [to_decimal(size, field="family_size") for size in family_sizes]
    if any(size < 0 for size in sizes):
        raise ValidationError("a family cannot have a negative size", field="family_sizes")
    count = Decimal(len(sizes))
    mean = sum(sizes, Decimal(0)) / count
    if mean == 0:
        raise ValidationError("no offspring at all", field="family_sizes")
    variance = sum(((size - mean) ** 2 for size in sizes), Decimal(0)) / count
    denominator = mean - 1 + variance / mean
    if denominator <= 0:
        raise ValidationError("these families cannot support a variance estimate", field="sizes")
    return (count * mean - 1) / denominator


@dataclass
class Pedigree:
    """Who came from whom, far enough back to keep sibs apart."""

    parents: dict[str, Family] = field(default_factory=dict)

    def record(self, offspring: str, family: Family) -> str:
        """File a fish against the family it came from."""

        code = normalise_code(offspring, field="offspring")
        if code in self.parents:
            raise ValidationError(f"{code} already has parents on file", field="offspring")
        if code in (family.dam, family.sire):
            raise ValidationError("a fish cannot be its own parent", field="offspring")
        self.parents[code] = family
        return code

    def family_of(self, tag: str) -> Family | None:
        return self.parents.get(normalise_code(tag, field="tag"))

    def ancestors(self, tag: str, generations: int = 3) -> set[str]:
        """Every parent, grandparent and so on, up to a depth."""

        if generations < 1:
            raise ValidationError("look back at least one generation", field="generations")
        found: set[str] = set()
        frontier = [normalise_code(tag, field="tag")]
        for _ in range(generations):
            following: list[str] = []
            for fish in frontier:
                family = self.parents.get(fish)
                if family is None:
                    continue
                for parent in (family.dam, family.sire):
                    if parent not in found:
                        found.add(parent)
                        following.append(parent)
            frontier = following
        return found

    def relatedness(self, first: str, second: str, generations: int = 3) -> Decimal:
        """A blunt shared ancestor score, between zero and one.

        This is not a coefficient of kinship and does not pretend to be. It is
        the share of one fish's known ancestors that also turn up in the other's,
        which is what a spawning crew can actually act on at the shed door.
        """

        left = self.ancestors(first, generations)
        right = self.ancestors(second, generations)
        if not left or not right:
            return Decimal(0)
        shared = left & right
        return safe_divide(len(shared), min(len(left), len(right)), field="ancestors")

    def are_full_sibs(self, first: str, second: str) -> bool:
        left = self.family_of(first)
        right = self.family_of(second)
        return left is not None and left == right

    def check_mating(self, dam: str, sire: str, *, limit: Number = "0.5") -> None:
        """Refuse a mating that is too close, with the rule named."""

        ceiling = to_decimal(limit, field="limit")
        if self.are_full_sibs(dam, sire):
            raise PolicyError(f"{dam} and {sire} are full sibs", rule="pedigree.full_sibs")
        score = self.relatedness(dam, sire)
        if score > ceiling:
            raise PolicyError(
                f"{dam} and {sire} share {score:.0%} of their known ancestry",
                rule="pedigree.relatedness",
            )

    def contributions(self) -> Counter[str]:
        """How many offspring each parent has on file."""

        counts: Counter[str] = Counter()
        for family in self.parents.values():
            counts[family.dam] += 1
            counts[family.sire] += 1
        return counts

    def census(self) -> Decimal:
        """The effective population of everything on file."""

        dams = {family.dam for family in self.parents.values()}
        sires = {family.sire for family in self.parents.values()}
        return effective_population(len(sires), len(dams))
