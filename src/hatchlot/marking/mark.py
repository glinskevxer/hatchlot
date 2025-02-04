"""Marks and tags, and the codes that have to survive the ocean.

A hatchery fish is marked so somebody can tell it from a wild one, and tagged so
somebody can tell which release group it came from. Those are two different jobs
and they are done with different equipment, which is why a fish can carry a clip
and a tag and neither one implies the other.

The coded wire tag code is the part with a format worth enforcing. It is issued
by an agency, it identifies one release group for the life of that group, and a
transposed digit in it points at another hatchery's fish.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide

_TAG_CODE = re.compile(r"^(\d{2})-(\d{2})-(\d{2})$")


class MarkType(Enum):
    """What is done to the fish."""

    ADIPOSE_CLIP = "adipose_clip"
    CODED_WIRE_TAG = "coded_wire_tag"
    PIT_TAG = "pit_tag"
    OTOLITH = "otolith"
    ELASTOMER = "elastomer"

    @property
    def is_external(self) -> bool:
        """Whether an angler can see it without a machine."""

        return self in {MarkType.ADIPOSE_CLIP, MarkType.ELASTOMER}

    @property
    def carries_a_code(self) -> bool:
        """Whether the mark identifies a group rather than just a hatchery origin."""

        return self in {MarkType.CODED_WIRE_TAG, MarkType.PIT_TAG, MarkType.OTOLITH}

    @property
    def needs_detection(self) -> bool:
        return self is MarkType.CODED_WIRE_TAG


@dataclass(frozen=True, slots=True, order=True)
class TagCode:
    """A coded wire tag code: agency, year and series."""

    agency: int
    year: int
    series: int

    def __init__(self, text: str) -> None:
        cleaned = str(text).strip().replace(" ", "-").replace("/", "-")
        match = _TAG_CODE.match(cleaned)
        if match is None:
            raise ValidationError(f"{text!r} is not a tag code", field="tag_code")
        agency, year, series = (int(part) for part in match.groups())
        if agency < 1:
            raise ValidationError("an agency code starts at one", field="tag_code")
        if series < 1:
            raise ValidationError("a series starts at one", field="tag_code")
        object.__setattr__(self, "agency", agency)
        object.__setattr__(self, "year", year)
        object.__setattr__(self, "series", series)

    def __str__(self) -> str:
        return f"{self.agency:02d}-{self.year:02d}-{self.series:02d}"

    def successor(self) -> TagCode:
        """The next series in the same agency and year."""

        if self.series >= 99:
            raise ValidationError("that agency and year is out of series", field="tag_code")
        return TagCode(f"{self.agency:02d}-{self.year:02d}-{self.series + 1:02d}")

    def belongs_to(self, agency: int) -> bool:
        return self.agency == agency


@dataclass(frozen=True, slots=True)
class MarkPlan:
    """What a release group is supposed to carry when it leaves."""

    lot: str
    marks: tuple[MarkType, ...]
    tag_code: TagCode | None = None
    target_rate: Decimal = Decimal("1.0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "lot", normalise_code(self.lot, field="lot"))
        if not self.marks:
            raise ValidationError("a mark plan marks something", field="marks")
        for mark in self.marks:
            if not isinstance(mark, MarkType):
                raise ValidationError(f"{mark!r} is not a mark type", field="marks")
        if len(set(self.marks)) != len(self.marks):
            raise ValidationError("a mark is applied once", field="marks")
        if not 0 < self.target_rate <= 1:
            raise ValidationError("a target rate is a share", field="target_rate")
        if self.needs_a_code and self.tag_code is None:
            raise ValidationError("a coded wire tag plan needs a tag code", field="tag_code")

    @property
    def needs_a_code(self) -> bool:
        return MarkType.CODED_WIRE_TAG in self.marks

    @property
    def is_visible(self) -> bool:
        return any(mark.is_external for mark in self.marks)

    def fish_to_mark(self, population: Number) -> Decimal:
        """How many fish the plan says to mark out of a population."""

        held = require_positive(population, field="population")
        return (held * self.target_rate).to_integral_value(rounding="ROUND_HALF_UP")


def mark_rate(marked: Number, population: Number) -> Decimal:
    """The share of a group that carries the mark."""

    held = require_positive(population, field="population")
    applied = require_positive(marked, field="marked")
    if applied > held:
        raise ValidationError("more fish marked than there are", field="marked")
    return safe_divide(applied, held, field="population")


def is_double_index(plan: MarkPlan) -> bool:
    """Whether the group is set up so tagged and untagged fish can be told apart.

    A double index group carries a clip on some fish and a tag on others, which
    is how a fishery works out how many untagged hatchery fish it caught. It only
    works if both marks are on the plan.
    """

    return MarkType.ADIPOSE_CLIP in plan.marks and MarkType.CODED_WIRE_TAG in plan.marks
