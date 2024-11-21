"""Feed conversion, and the two versions of it that get confused.

Economic conversion is feed fed over weight gained, and it is what the budget is
written on. Biological conversion counts the fish that died as gain that was
paid for and never collected, so it is always the better looking number and it is
the one that says whether the feed itself is doing its job.

Reporting one and labelling it the other is the mistake this module exists to
stop, so both are here and neither is called just conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, require_non_negative, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity


@dataclass(frozen=True, slots=True)
class Conversion:
    """One period of feeding, with everything the two ratios need."""

    fed: Quantity
    opening_biomass: Quantity
    closing_biomass: Quantity
    mortality_biomass: Quantity

    def __post_init__(self) -> None:
        for name in ("fed", "opening_biomass", "closing_biomass", "mortality_biomass"):
            require_non_negative(getattr(self, name).to("kg").amount, field=name)

    @property
    def gain(self) -> Quantity:
        """What the raceway is heavier by, which is what the budget sees."""

        return self.closing_biomass - self.opening_biomass

    @property
    def biological_gain(self) -> Quantity:
        """Gain plus the weight that died, which is what the feed actually grew."""

        return self.gain + self.mortality_biomass

    @property
    def economic_ratio(self) -> Decimal:
        gained = self.gain.to("kg").amount
        if gained <= 0:
            raise ValidationError("nothing was gained to convert into", field="gain")
        return safe_divide(self.fed.to("kg").amount, gained, field="gain")

    @property
    def biological_ratio(self) -> Decimal:
        gained = self.biological_gain.to("kg").amount
        if gained <= 0:
            raise ValidationError("nothing was grown to convert into", field="gain")
        return safe_divide(self.fed.to("kg").amount, gained, field="gain")

    @property
    def efficiency(self) -> Decimal:
        """Gain over feed, the same thing the other way up, as a percentage."""

        return Decimal(100) / self.economic_ratio

    def is_plausible(self, *, ceiling: Number = 3) -> bool:
        """Whether a ratio is believable or points at a counting mistake.

        A conversion under a half means somebody has weighed the fish wrong. Over
        the ceiling means the feed is going out the drain, or the same thing.
        """

        limit = require_positive(ceiling, field="ceiling")
        try:
            ratio = self.economic_ratio
        except ValidationError:
            return False
        return Decimal("0.5") <= ratio <= limit


def feed_needed(gain: Quantity, ratio: Number) -> Quantity:
    """The feed a planned gain will take at an expected conversion."""

    wanted = require_positive(gain.to("kg").amount, field="gain")
    conversion = require_positive(ratio, field="ratio")
    return Quantity(wanted * conversion, "kg")


def gain_expected(fed: Quantity, ratio: Number) -> Quantity:
    """The gain a quantity of feed should produce at a conversion."""

    conversion = require_positive(ratio, field="ratio")
    return Quantity(fed.to("kg").amount / conversion, "kg")


def cost_per_gain(fed: Quantity, price_per_kg: Number, gain: Quantity) -> Decimal:
    """What a kilogram of fish cost in feed."""

    price = to_decimal(price_per_kg, field="price_per_kg")
    if price < 0:
        raise ValidationError("a price cannot be negative", field="price_per_kg")
    gained = require_positive(gain.to("kg").amount, field="gain")
    return fed.to("kg").amount * price / gained


def combined(periods: list[Conversion]) -> Conversion:
    """Add several periods into one, which is how a season is reported.

    Adding the ratios and dividing by the count is wrong and common. This adds
    the weights and takes the ratio once at the end.
    """

    if not periods:
        raise ValidationError("no periods to combine", field="periods")
    fed = Quantity(0, "kg")
    opening = periods[0].opening_biomass
    closing = periods[-1].closing_biomass
    dead = Quantity(0, "kg")
    for period in periods:
        fed = fed + period.fed
        dead = dead + period.mortality_biomass
    return Conversion(
        fed=fed,
        opening_biomass=opening,
        closing_biomass=closing,
        mortality_biomass=dead,
    )
