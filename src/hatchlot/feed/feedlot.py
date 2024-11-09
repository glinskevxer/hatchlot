"""Feed lots, and the label that has to travel with them.

Feed arrives on a pallet with a lot number, a manufacture date and a guaranteed
analysis printed on the tag. All three matter later. The lot number is what a
fish health investigation asks for first. The date decides whether the vitamins
in it are still worth anything. The analysis is what the ration and the effluent
numbers are both worked out from.

Pellet size is not a label detail either. A pellet too big for the fish is not
eaten and a pellet too small is not efficient, so the size a lot carries decides
which fish it can be fed to at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import add_months, parse_date
from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_non_negative, require_range
from ..quantities.base import Quantity


class FeedForm(Enum):
    """How the feed is made, which decides how it sinks and how it keeps."""

    STARTER = "starter"
    CRUMBLE = "crumble"
    PELLET = "pellet"
    EXTRUDED = "extruded"

    @property
    def floats(self) -> bool:
        return self is FeedForm.EXTRUDED


@dataclass(frozen=True, slots=True)
class Analysis:
    """The guaranteed analysis off the tag, as fractions of the feed."""

    protein: Decimal
    fat: Decimal
    fibre: Decimal
    ash: Decimal
    moisture: Decimal

    def __post_init__(self) -> None:
        for name in ("protein", "fat", "fibre", "ash", "moisture"):
            require_range(getattr(self, name), 0, 1, field=name)
        if self.total > 1:
            raise ValidationError("the analysis adds to more than the feed", field="analysis")

    @property
    def total(self) -> Decimal:
        return self.protein + self.fat + self.fibre + self.ash + self.moisture

    @property
    def carbohydrate(self) -> Decimal:
        """What is left when everything named is taken out."""

        return Decimal(1) - self.total

    @property
    def digestible_energy(self) -> Decimal:
        """Megajoules per kilogram, on the usual coefficients for a fish feed."""

        return (
            self.protein * Decimal("18.0")
            + self.fat * Decimal("35.5")
            + self.carbohydrate * Decimal("12.6")
        )

    @property
    def dry_matter(self) -> Decimal:
        return Decimal(1) - self.moisture


@dataclass
class FeedLot:
    """One lot of feed as it sits in the store."""

    code: str
    product: str
    form: FeedForm
    pellet_mm: Decimal
    analysis: Analysis
    made_on: date
    quantity: Quantity
    supplier: str = ""
    shelf_months: int = 6
    medicated: bool = False

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="feed_lot")
        if not self.product.strip():
            raise ValidationError("a feed lot needs a product name", field="product")
        self.product = self.product.strip()
        if not isinstance(self.form, FeedForm):
            raise ValidationError(f"{self.form!r} is not a feed form", field="form")
        self.pellet_mm = require_range(self.pellet_mm, "0.2", 30, field="pellet_mm")
        self.made_on = parse_date(self.made_on)
        require_non_negative(self.quantity.to("kg").amount, field="quantity")
        if self.shelf_months < 1:
            raise ValidationError("a shelf life is at least a month", field="shelf_months")

    @property
    def expires_on(self) -> date:
        return add_months(self.made_on, self.shelf_months)

    def is_expired(self, as_of: object) -> bool:
        return parse_date(as_of) > self.expires_on

    def days_left(self, as_of: object) -> int:
        return (self.expires_on - parse_date(as_of)).days

    def check_usable(self, as_of: object) -> None:
        """Refuse feed that is out of date or already gone."""

        if self.is_expired(as_of):
            raise PolicyError(
                f"feed lot {self.code} expired on {self.expires_on}", rule="feed.expired"
            )
        if self.quantity.to("kg").amount <= 0:
            raise PolicyError(f"feed lot {self.code} is empty", rule="feed.empty")

    def suits(self, fish_length: Quantity) -> bool:
        """Whether the pellet is the right size for a fish of this length.

        The working rule is a pellet somewhere between two and four percent of
        the fish's length, which is what the feed charts come out at.
        """

        millimetres = fish_length.to("mm").amount
        if millimetres <= 0:
            raise ValidationError("a fish has a length", field="fish_length")
        return millimetres * Decimal("0.02") <= self.pellet_mm <= millimetres * Decimal("0.05")

    def draw(self, amount: Quantity) -> Quantity:
        """Take feed out, refusing more than the lot holds."""

        wanted = require_non_negative(amount.to("kg").amount, field="amount")
        held = self.quantity.to("kg").amount
        if wanted > held:
            raise ValidationError(
                f"feed lot {self.code} holds {held} kg, not {wanted}", field="amount"
            )
        self.quantity = Quantity(held - wanted, "kg")
        return self.quantity

    def receive(self, amount: Quantity) -> Quantity:
        added = require_non_negative(amount.to("kg").amount, field="amount")
        self.quantity = Quantity(self.quantity.to("kg").amount + added, "kg")
        return self.quantity


def energy_of(lot: FeedLot, amount: Quantity) -> Decimal:
    """Megajoules of digestible energy in a quantity of a feed."""

    kilograms = require_non_negative(amount.to("kg").amount, field="amount")
    return lot.analysis.digestible_energy * kilograms


def protein_of(lot: FeedLot, amount: Quantity) -> Quantity:
    """The protein in a quantity of a feed."""

    kilograms = require_non_negative(amount.to("kg").amount, field="amount")
    return Quantity(kilograms * lot.analysis.protein, "kg")


def pellet_for(fish_length: Quantity, *, share: Number = "0.03") -> Quantity:
    """The pellet size a fish of a length wants."""

    millimetres = fish_length.to("mm").amount
    if millimetres <= 0:
        raise ValidationError("a fish has a length", field="fish_length")
    fraction = require_range(share, "0.01", "0.06", field="share")
    return Quantity(millimetres * fraction, "mm")
