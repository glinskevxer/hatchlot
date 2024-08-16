"""Picking, and telling an ordinary day's dead eggs from a problem.

Somebody walks the incubation room every day and pulls out what has gone white.
The count that comes off a tray is meaningless on its own, because a big lot
loses more eggs than a small one for the same reason. What matters is the rate,
and whether today's rate is out of line with the fortnight behind it.

Two alarms sit on that, and they catch different things. A flat ceiling catches
a disaster. A comparison against the lot's own recent history catches the slow
start of one, which is the one nobody notices.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..journal import Journal
from ..numeric import Number, require_positive, safe_divide, to_decimal
from .eggslot import EggLot, EggStage, LossCause


class PickAlert(Enum):
    """What a day's picking looks like."""

    NORMAL = "normal"
    ELEVATED = "elevated"
    SPIKE = "spike"

    @property
    def needs_a_look(self) -> bool:
        return self is not PickAlert.NORMAL


@dataclass(frozen=True, slots=True, order=True)
class Pick:
    """One day's dead eggs off one lot."""

    day: date
    lot: str
    count: Decimal
    picked_by: str
    cause: LossCause = LossCause.PICKED

    def __init__(
        self,
        day: object,
        lot: str,
        count: Number,
        picked_by: str,
        cause: LossCause = LossCause.PICKED,
    ) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        object.__setattr__(self, "count", require_positive(count, field="count"))
        if not picked_by.strip():
            raise ValidationError("a pick needs whoever made it", field="picked_by")
        object.__setattr__(self, "picked_by", picked_by.strip())
        if not isinstance(cause, LossCause):
            raise ValidationError(f"{cause!r} is not a loss cause", field="cause")
        object.__setattr__(self, "cause", cause)


@dataclass(frozen=True, slots=True)
class PickLimits:
    """The two thresholds, one absolute and one relative."""

    daily_ceiling: Decimal = Decimal("0.01")
    spike_multiple: Decimal = Decimal(3)
    history_days: int = 14

    def __post_init__(self) -> None:
        require_positive(self.daily_ceiling, field="daily_ceiling")
        require_positive(self.spike_multiple, field="spike_multiple")
        if self.history_days < 2:
            raise ValidationError("a history needs at least two days", field="history_days")


class PickingLog:
    """Every pick, over every lot."""

    def __init__(self, picks: Iterable[Pick] = ()) -> None:
        self._journal: Journal[Pick] = Journal(
            day_of=lambda pick: pick.day, key_of=lambda pick: pick.lot
        )
        self._journal.extend(picks)

    def record(self, pick: Pick) -> Pick:
        return self._journal.record(pick)

    def __len__(self) -> int:
        return len(self._journal)

    def for_lot(self, lot: str) -> tuple[Pick, ...]:
        return self._journal.for_key(lot)

    def within(self, window: DateRange) -> tuple[Pick, ...]:
        return self._journal.within(window)

    def total_for(self, lot: str) -> Decimal:
        return sum((pick.count for pick in self.for_lot(lot)), Decimal(0))

    def on_day(self, lot: str, day: object) -> Decimal:
        when = parse_date(day)
        return sum((pick.count for pick in self.for_lot(lot) if pick.day == when), Decimal(0))

    def daily_rate(self, lot: str, day: object, standing: Number) -> Decimal:
        """The share of a lot picked on one day."""

        held = require_positive(standing, field="standing")
        return safe_divide(self.on_day(lot, day), held, field="standing")

    def recent_mean(self, lot: str, day: object, days: int) -> Decimal:
        """The mean daily pick over the days before a day, not counting it."""

        if days < 1:
            raise ValidationError("a history needs at least one day", field="days")
        when = parse_date(day)
        window = DateRange(when - timedelta(days=days), when - timedelta(days=1))
        picks = [pick for pick in self.for_lot(lot) if pick.day in window]
        if not picks:
            return Decimal(0)
        return sum((pick.count for pick in picks), Decimal(0)) / Decimal(days)

    def classify(
        self, lot: str, day: object, standing: Number, limits: PickLimits | None = None
    ) -> PickAlert:
        """Read a day's picking against both thresholds."""

        rules = limits or PickLimits()
        today = self.on_day(lot, day)
        if today == 0:
            return PickAlert.NORMAL
        if self.daily_rate(lot, day, standing) > rules.daily_ceiling:
            return PickAlert.SPIKE
        mean = self.recent_mean(lot, day, rules.history_days)
        if mean > 0 and today > mean * rules.spike_multiple:
            return PickAlert.ELEVATED
        return PickAlert.NORMAL


def apply_pick(lot: EggLot, pick: Pick) -> Decimal:
    """Take a pick off a lot's count and hand back what is left."""

    if str(lot.code) != pick.lot:
        raise ValidationError(f"pick is for {pick.lot}, not {lot.code}", field="lot")
    lot.record_loss(pick.day, pick.count, pick.cause)
    return lot.count


def cumulative_loss(log: PickingLog, lot: str, green_count: Number) -> Decimal:
    """The share of a lot's green count picked out so far."""

    green = require_positive(green_count, field="green_count")
    return safe_divide(log.total_for(lot), green, field="green_count")


def picked_by_stage(lot: EggLot) -> dict[EggStage, Decimal]:
    """Picks split by the stage the lot was in, off the lot's own record."""

    totals: dict[EggStage, Decimal] = {}
    for entry in lot.losses:
        if entry.cause is not LossCause.PICKED:
            continue
        totals[entry.stage] = totals.get(entry.stage, Decimal(0)) + to_decimal(entry.count)
    return totals
