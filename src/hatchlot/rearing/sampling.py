"""Weighing a few fish to find out about a lot of them.

Nobody weighs fifty thousand fish. A crew nets a few hundred, counts them,
weighs them together, and the mean weight of that sample becomes the mean weight
of the lot. Everything downstream leans on it: the biomass, the feed, the
loading, the number of fish on the truck.

So the sample has to answer for itself. Too few fish and the mean is noise. Two
samples off the same lot that disagree by a quarter mean somebody netted the top
of the raceway both times. Both of those are refusals here rather than notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import parse_date
from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity

# The smallest sample a station will accept, and the share of the lot below
# which a sample is treated as a spot check rather than an estimate.
MINIMUM_SAMPLE = 100


@dataclass(frozen=True, slots=True, order=True)
class Sample:
    """One netful: how many fish, and what they weighed together."""

    day: date
    lot: str
    fish: int
    weight: Quantity
    taken_by: str

    def __init__(self, day: object, lot: str, fish: int, weight: Quantity, taken_by: str) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        if fish < 1:
            raise ValidationError("a sample has fish in it", field="fish")
        object.__setattr__(self, "fish", fish)
        require_positive(weight.to("g").amount, field="weight")
        object.__setattr__(self, "weight", weight)
        if not taken_by.strip():
            raise ValidationError("a sample needs whoever took it", field="taken_by")
        object.__setattr__(self, "taken_by", taken_by.strip())

    @property
    def mean_weight(self) -> Quantity:
        return Quantity(self.weight.to("g").amount / Decimal(self.fish), "g")

    @property
    def fish_per_pound(self) -> Decimal:
        return safe_divide(1, self.mean_weight.to("lb").amount, field="mean_weight")

    def is_large_enough(self, minimum: int = MINIMUM_SAMPLE) -> bool:
        return self.fish >= minimum


@dataclass(frozen=True, slots=True)
class SampleSummary:
    """Several samples off one lot, and how well they agree."""

    lot: str
    samples: int
    fish: int
    mean_weight: Quantity
    spread: Decimal

    @property
    def coefficient_of_variation(self) -> Decimal:
        """The spread as a share of the mean, which is the number to judge on."""

        return safe_divide(self.spread, self.mean_weight.to("g").amount, field="mean_weight")

    def is_consistent(self, *, limit: Number = "0.15") -> bool:
        return self.coefficient_of_variation <= to_decimal(limit, field="limit")


def summarise_samples(samples: list[Sample]) -> SampleSummary:
    """Combine samples off one lot into a mean and a spread.

    The mean is weighted by how many fish each sample held, because a sample of
    four hundred says more than one of forty and averaging the two means treats
    them alike.
    """

    if not samples:
        raise ValidationError("no samples to summarise", field="samples")
    lots = {sample.lot for sample in samples}
    if len(lots) != 1:
        raise ValidationError("these samples are off different lots", field="samples")
    fish = sum(sample.fish for sample in samples)
    total = sum((sample.weight.to("g").amount for sample in samples), Decimal(0))
    mean = total / Decimal(fish)
    if len(samples) == 1:
        spread = Decimal(0)
    else:
        variance = sum(
            (
                Decimal(sample.fish) * (sample.mean_weight.to("g").amount - mean) ** 2
                for sample in samples
            ),
            Decimal(0),
        ) / Decimal(fish)
        spread = variance.sqrt()
    return SampleSummary(
        lot=samples[0].lot,
        samples=len(samples),
        fish=fish,
        mean_weight=Quantity(mean, "g"),
        spread=spread,
    )


def check_sample(sample: Sample, population: Number, *, minimum: int = MINIMUM_SAMPLE) -> None:
    """Refuse a sample too small to stand for the lot it came out of."""

    held = require_positive(population, field="population")
    if sample.fish >= held:
        return
    if not sample.is_large_enough(minimum):
        raise PolicyError(
            f"a sample of {sample.fish} fish will not stand for {held}",
            rule="sampling.too_small",
        )


def estimate_population(biomass: Quantity, mean_weight: Quantity) -> Decimal:
    """How many fish a biomass is, at a mean weight."""

    require_positive(mean_weight.to("g").amount, field="mean_weight")
    return safe_divide(biomass.to("g").amount, mean_weight.to("g").amount, field="mean_weight")


def estimate_biomass(population: Number, mean_weight: Quantity) -> Quantity:
    """What a population weighs, at a mean weight."""

    count = require_positive(population, field="population")
    return Quantity(count * mean_weight.to("kg").amount, "kg")


def growth_between(first: Sample, second: Sample) -> Decimal:
    """The share a lot's mean weight grew between two samples."""

    if first.lot != second.lot:
        raise ValidationError("these samples are off different lots", field="lot")
    if second.day <= first.day:
        raise ValidationError("the second sample is not later", field="day")
    start = first.mean_weight.to("g").amount
    end = second.mean_weight.to("g").amount
    return safe_divide(end - start, start, field="mean_weight")
