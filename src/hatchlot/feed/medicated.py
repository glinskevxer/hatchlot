"""Medicated feed, and the hold it puts on a lot afterwards.

A prescription is written as a dose per kilogram of fish per day, and the feed
mill needs an inclusion rate per kilogram of feed. The two are only the same
number if you know the feeding rate, so the conversion goes through the ration
and the ration goes through the water temperature. Get that wrong and the fish
are underdosed, which breeds resistance, or overdosed, which fails a residue
test.

The withdrawal period is counted in degree days rather than days, because a drug
clears a fish at the rate the fish is living, and a cold March is a longer
withdrawal than a warm one. That is the rule that catches people out, so the
release hold is worked out against a temperature record rather than a calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity
from ..water.thermal import GapPolicy, ThermalSeries


class Drug(Enum):
    """The compounds a coldwater hatchery is licensed to feed."""

    OXYTETRACYCLINE = "oxytetracycline"
    FLORFENICOL = "florfenicol"
    SULFADIMETHOXINE = "sulfadimethoxine"

    @property
    def withdrawal_degree_days(self) -> Decimal:
        """Celsius degree days that must pass before a treated fish is released."""

        return {
            "oxytetracycline": Decimal(400),
            "florfenicol": Decimal(180),
            "sulfadimethoxine": Decimal(300),
        }[self.value]

    @property
    def label_dose_mg_per_kg(self) -> Decimal:
        """The label dose in milligrams per kilogram of fish per day."""

        return {
            "oxytetracycline": Decimal("75"),
            "florfenicol": Decimal("10"),
            "sulfadimethoxine": Decimal("50"),
        }[self.value]

    @property
    def label_days(self) -> int:
        return {"oxytetracycline": 10, "florfenicol": 10, "sulfadimethoxine": 5}[self.value]


@dataclass(frozen=True, slots=True)
class Prescription:
    """One written order to feed a drug to a lot."""

    code: str
    lot: str
    drug: Drug
    dose_mg_per_kg: Decimal
    days: int
    start: date
    prescribed_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="prescription"))
        object.__setattr__(self, "lot", normalise_code(self.lot, field="lot"))
        if not isinstance(self.drug, Drug):
            raise ValidationError(f"{self.drug!r} is not a drug", field="drug")
        object.__setattr__(
            self, "dose_mg_per_kg", require_positive(self.dose_mg_per_kg, field="dose")
        )
        if self.days < 1:
            raise ValidationError("a course runs at least a day", field="days")
        object.__setattr__(self, "start", parse_date(self.start))
        if not self.prescribed_by.strip():
            raise ValidationError("a prescription needs a prescriber", field="prescribed_by")
        object.__setattr__(self, "prescribed_by", self.prescribed_by.strip())

    @property
    def window(self) -> DateRange:
        return DateRange(self.start, self.start + timedelta(days=self.days - 1))

    @property
    def is_off_label(self) -> bool:
        """Whether the order departs from the label, which needs a vet's name on it."""

        return (
            self.dose_mg_per_kg != self.drug.label_dose_mg_per_kg
            or self.days != self.drug.label_days
        )

    def daily_drug(self, biomass: Quantity) -> Decimal:
        """Milligrams of drug the lot needs in a day."""

        kilograms = require_positive(biomass.to("kg").amount, field="biomass")
        return self.dose_mg_per_kg * kilograms

    def total_drug(self, biomass: Quantity) -> Decimal:
        return self.daily_drug(biomass) * Decimal(self.days)


def inclusion_rate(prescription: Prescription, feeding_rate_percent: Number) -> Decimal:
    """Milligrams of drug per kilogram of feed, which is what the mill needs.

    The feeding rate is the bridge. A lot fed at two percent of body weight gets
    fifty times the dose per kilogram of feed that the fish get per kilogram of
    fish, so a mistake here is a factor of fifty rather than a rounding.
    """

    share = require_positive(feeding_rate_percent, field="feeding_rate_percent")
    if share > 20:
        raise ValidationError("that is not a feeding rate", field="feeding_rate_percent")
    return prescription.dose_mg_per_kg * Decimal(100) / share


def medicated_feed_needed(
    prescription: Prescription, biomass: Quantity, feeding_rate_percent: Number
) -> Quantity:
    """How much medicated feed the whole course takes."""

    share = require_positive(feeding_rate_percent, field="feeding_rate_percent")
    daily = biomass.to("kg").amount * share / Decimal(100)
    return Quantity(daily * Decimal(prescription.days), "kg")


@dataclass(frozen=True, slots=True)
class Withdrawal:
    """The hold a course leaves on a lot after the last dose."""

    lot: str
    drug: Drug
    last_dose: date
    required_degree_days: Decimal

    def accumulated(self, series: ThermalSeries, as_of: object) -> Decimal:
        """Degree days since the last dose, on the record."""

        when = parse_date(as_of)
        if when <= self.last_dose:
            return Decimal(0)
        return series.accumulate(
            DateRange(self.last_dose + timedelta(days=1), when),
            policy=GapPolicy.CARRY_FORWARD,
        )

    def is_clear(self, series: ThermalSeries, as_of: object) -> bool:
        return self.accumulated(series, as_of) >= self.required_degree_days

    def remaining(self, series: ThermalSeries, as_of: object) -> Decimal:
        left = self.required_degree_days - self.accumulated(series, as_of)
        return left if left > 0 else Decimal(0)

    def clears_on(
        self, series: ThermalSeries, *, assumed_celsius: Number | None = None
    ) -> date | None:
        """The day the hold lifts, projected on an assumed water if need be."""

        found = series.day_units_reach(
            self.last_dose + timedelta(days=1),
            self.required_degree_days,
            policy=GapPolicy.CARRY_FORWARD,
        )
        if found is not None:
            return found
        if assumed_celsius is None:
            return None
        water = require_positive(assumed_celsius, field="assumed_celsius")
        days = int((self.required_degree_days / water).to_integral_value(rounding="ROUND_CEILING"))
        return self.last_dose + timedelta(days=days)

    def check(self, series: ThermalSeries, as_of: object) -> None:
        """Refuse a release inside the withdrawal, with the shortfall named."""

        if not self.is_clear(series, as_of):
            raise PolicyError(
                f"{self.lot} is {self.remaining(series, as_of)} degree days short of "
                f"clearing {self.drug.value}",
                rule="feed.withdrawal",
            )


def withdrawal_for(prescription: Prescription, *, last_dose: object | None = None) -> Withdrawal:
    """The hold a prescription leaves behind it."""

    end = parse_date(last_dose) if last_dose is not None else prescription.window.end
    if end < prescription.start:
        raise ValidationError("the last dose is before the course started", field="last_dose")
    return Withdrawal(
        lot=prescription.lot,
        drug=prescription.drug,
        last_dose=end,
        required_degree_days=prescription.drug.withdrawal_degree_days,
    )


def dose_delivered(fed: Quantity, inclusion_mg_per_kg: Number, biomass: Quantity) -> Decimal:
    """What dose the fish actually got, off the feeding record.

    A course that was written correctly and fed short is the common failure, and
    the only way to see it is to work the dose back out of what was fed.
    """

    rate = require_positive(inclusion_mg_per_kg, field="inclusion_mg_per_kg")
    kilograms = require_positive(biomass.to("kg").amount, field="biomass")
    return safe_divide(fed.to("kg").amount * rate, kilograms, field="biomass")


def is_course_complete(
    prescription: Prescription, delivered_mg_per_kg: Number, *, tolerance: Number = "0.9"
) -> bool:
    """Whether enough of the course actually went in to count as a course."""

    share = to_decimal(tolerance, field="tolerance")
    if not 0 < share <= 1:
        raise ValidationError("that is not a share of the course", field="tolerance")
    wanted = prescription.dose_mg_per_kg * Decimal(prescription.days)
    return to_decimal(delivered_mg_per_kg, field="delivered") >= wanted * share
