"""The release itself, and everything that has to be true before it happens.

This is the last gate in the package and it is where the other gates are
collected. A release needs a request that is open and in its window, a marking
run somebody accepted, a lot with no health hold and no drug withdrawal
outstanding, and a truck that was tempered before the fish went over the side.

Each of those lives in the module that owns it. What is here is the order they
are checked in and the record of a release that passed them, because the record
is what somebody will ask for in two years when a tagged fish turns up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..journal import JournalLog
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from .haul import HaulLoad, check_tempering
from .request import StockingRequest


class ReleaseKind(Enum):
    """How the fish went into the water."""

    DIRECT = "direct"
    ACCLIMATION = "acclimation"
    VOLITIONAL = "volitional"
    TRANSFER = "transfer"

    @property
    def is_final(self) -> bool:
        """A transfer to another station is not a release into a fishery."""

        return self is not ReleaseKind.TRANSFER


@dataclass(frozen=True, slots=True)
class Release:
    """One load of fish, into one water, on one day."""

    code: str
    day: date
    lot: str
    water: str
    request: str
    fish: Decimal
    mean_weight: Quantity
    kind: ReleaseKind
    released_by: str
    truck_water: Temperature | None = None
    receiving_water: Temperature | None = None
    tag_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="release"))
        object.__setattr__(self, "day", parse_date(self.day))
        object.__setattr__(self, "lot", normalise_code(self.lot, field="lot"))
        object.__setattr__(self, "water", normalise_code(self.water, field="water"))
        object.__setattr__(self, "request", normalise_code(self.request, field="request"))
        object.__setattr__(self, "fish", require_positive(self.fish, field="fish"))
        require_positive(self.mean_weight.to("g").amount, field="mean_weight")
        if not isinstance(self.kind, ReleaseKind):
            raise ValidationError(f"{self.kind!r} is not a release kind", field="kind")
        if not self.released_by.strip():
            raise ValidationError("a release needs whoever made it", field="released_by")
        object.__setattr__(self, "released_by", self.released_by.strip())

    @property
    def biomass(self) -> Quantity:
        return Quantity(self.fish * self.mean_weight.to("kg").amount, "kg")

    @property
    def fish_per_pound(self) -> Decimal:
        return safe_divide(1, self.mean_weight.to("lb").amount, field="mean_weight")

    @property
    def was_tempered(self) -> bool:
        return self.truck_water is not None and self.receiving_water is not None


def release_fish(
    request: StockingRequest,
    haul: HaulLoad,
    *,
    code: str,
    day: object,
    lot: str,
    kind: ReleaseKind,
    released_by: str,
    receiving_water: Temperature,
    marking_accepted: bool = True,
    withdrawal_clear: bool = True,
    health_hold: bool = False,
    tempering_limit: Number = 2,
    tag_code: str = "",
) -> Release:
    """Run the gates in order and hand back the record if they all pass.

    The order is deliberate. The health checks come first because they are the
    ones that make the answer no whatever else is true, and hearing about a
    tempering problem when the lot was never releasable wastes a morning.
    """

    when = parse_date(day)
    if health_hold:
        raise PolicyError(f"{lot} is under a health hold", rule="release.health_hold")
    if not withdrawal_clear:
        raise PolicyError(f"{lot} has a drug withdrawal outstanding", rule="release.withdrawal")
    if not marking_accepted:
        raise PolicyError(f"{lot} has no accepted marking run", rule="release.marking")
    if request.state.is_closed:
        raise PolicyError(
            f"request {request.code} is {request.state.value}", rule="release.request_closed"
        )
    if not request.accepts_day(when):
        raise PolicyError(f"{when} is outside {request.window}", rule="release.window")
    if not request.accepts_size(haul.mean_weight):
        raise PolicyError(
            f"{haul.mean_weight.rounded(1)} is outside what {request.code} will take",
            rule="release.size",
        )
    haul.check()
    check_tempering(haul.load_water, receiving_water, limit_celsius=tempering_limit)
    request.deliver(haul.fish, when)
    return Release(
        code=code,
        day=when,
        lot=lot,
        water=request.water,
        request=request.code,
        fish=haul.fish,
        mean_weight=haul.mean_weight,
        kind=kind,
        released_by=released_by,
        truck_water=haul.load_water,
        receiving_water=receiving_water,
        tag_code=tag_code,
    )


class ReleaseRegister(JournalLog[Release]):
    """Every release the station has made."""

    def __init__(self) -> None:
        super().__init__(lambda entry: entry.day, lambda entry: entry.lot)

    def for_lot(self, lot: str) -> tuple[Release, ...]:
        return self._for_key(lot)

    def for_water(self, water: str) -> tuple[Release, ...]:
        code = normalise_code(water, field="water")
        return tuple(entry for entry in self.all() if entry.water == code)

    def for_request(self, request: str) -> tuple[Release, ...]:
        code = normalise_code(request, field="request")
        return tuple(entry for entry in self.all() if entry.request == code)

    def fish_released(self, lot: str | None = None) -> Decimal:
        entries = self.for_lot(lot) if lot else self.all()
        return sum((entry.fish for entry in entries if entry.kind.is_final), Decimal(0))

    def biomass_released(self, lot: str | None = None) -> Quantity:
        entries = self.for_lot(lot) if lot else self.all()
        total = Quantity(0, "kg")
        for entry in entries:
            if entry.kind.is_final:
                total = total + entry.biomass
        return total

    def waters(self) -> tuple[str, ...]:
        return tuple(sorted({entry.water for entry in self.all()}))

    def untempered(self) -> tuple[Release, ...]:
        """Releases with no tempering record, which is an audit finding."""

        return tuple(entry for entry in self.all() if not entry.was_tempered)
