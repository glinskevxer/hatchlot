"""The distribution season, read from the requests and the releases together.

Neither side tells the story alone. The releases say what went out, which looks
like a good year in any year the station had fish. The requests say what was
asked for, which is what the station is judged against. The gap between them,
split by why, is the report that actually gets read.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..calendar import DateRange
from ..errors import ValidationError
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from .release import ReleaseRegister
from .request import RequestBook, RequestState


@dataclass(frozen=True, slots=True)
class DistributionSummary:
    """One season of getting fish out of the door."""

    window: DateRange
    requests: int
    filled: int
    partial: int
    declined: int
    lapsed: int
    fish_requested: Decimal
    fish_released: Decimal
    biomass_released: Quantity
    waters: tuple[str, ...]

    @property
    def fill_rate(self) -> Decimal:
        if self.fish_requested == 0:
            return Decimal(0)
        return safe_divide(self.fish_released, self.fish_requested, field="requested")

    @property
    def unmet(self) -> Decimal:
        gap = self.fish_requested - self.fish_released
        return gap if gap > 0 else Decimal(0)

    @property
    def closed_without_fish(self) -> int:
        return self.declined + self.lapsed

    def line(self) -> str:
        return (
            f"{self.window}: {self.fish_released:.0f} of {self.fish_requested:.0f} fish "
            f"to {len(self.waters)} waters, {self.filled} of {self.requests} requests filled"
        )


def summarise_distribution(
    book: RequestBook, releases: ReleaseRegister, window: DateRange
) -> DistributionSummary:
    """Pull the season together over a window."""

    inside = [request for request in book.all() if request.window.overlaps(window)]
    released = [entry for entry in releases.within(window) if entry.kind.is_final]
    biomass = Quantity(0, "kg")
    for entry in released:
        biomass = biomass + entry.biomass
    return DistributionSummary(
        window=window,
        requests=len(inside),
        filled=len([r for r in inside if r.state is RequestState.FILLED]),
        partial=len([r for r in inside if r.state is RequestState.PARTIAL]),
        declined=len([r for r in inside if r.state is RequestState.DECLINED]),
        lapsed=len([r for r in inside if r.state is RequestState.LAPSED]),
        fish_requested=sum((request.fish for request in inside), Decimal(0)),
        fish_released=sum((entry.fish for entry in released), Decimal(0)),
        biomass_released=biomass,
        waters=tuple(sorted({entry.water for entry in released})),
    )


def by_water(releases: ReleaseRegister, window: DateRange) -> dict[str, Decimal]:
    """Fish released into each water inside a window."""

    totals: dict[str, Decimal] = {}
    for entry in releases.within(window):
        if entry.kind.is_final:
            totals[entry.water] = totals.get(entry.water, Decimal(0)) + entry.fish
    return totals


def by_lot(releases: ReleaseRegister, window: DateRange) -> dict[str, Decimal]:
    """Fish released out of each lot inside a window."""

    totals: dict[str, Decimal] = {}
    for entry in releases.within(window):
        totals[entry.lot] = totals.get(entry.lot, Decimal(0)) + entry.fish
    return totals


def biggest_shortfall(book: RequestBook) -> str | None:
    """The open request furthest from being filled, which is where to look first."""

    open_requests = [request for request in book.open_requests() if request.outstanding > 0]
    if not open_requests:
        return None
    worst = max(open_requests, key=lambda request: request.outstanding)
    return worst.code


def cost_per_fish(total_cost: Number, released: Number) -> Decimal:
    """What each fish out of the door cost, on whatever cost is passed in."""

    count = require_positive(released, field="released")
    cost = require_positive(total_cost, field="total_cost")
    return cost / count


def release_share(summary: DistributionSummary, water: str, releases: ReleaseRegister) -> Decimal:
    """How much of a season's release went into one water."""

    if summary.fish_released == 0:
        raise ValidationError("nothing was released", field="released")
    totals = by_water(releases, summary.window)
    from ..identifiers import normalise_code

    code = normalise_code(water, field="water")
    return safe_divide(totals.get(code, Decimal(0)), summary.fish_released, field="released")
