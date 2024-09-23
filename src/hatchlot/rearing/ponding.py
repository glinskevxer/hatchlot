"""The handover from the incubation room to the rearing units.

This is the one place in the package where a lot changes what kind of thing it
is. An egg lot ends and a rearing lot begins, and the two records have to agree
on the number of fish that crossed. That is why ponding is not a method on
either of them: it needs both, plus the ledger, plus the container it is going
into, and none of those should own it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import parse_date
from ..errors import PolicyError, StateError, ValidationError
from ..identifiers import LotCode
from ..incubation.eggslot import EggLot, EggStage
from ..numeric import Number, require_positive
from ..quantities.base import Quantity
from .container import Container
from .ledger import EntryKind, Ledger, LedgerEntry
from .lot import RearingLot


@dataclass(frozen=True, slots=True)
class Ponding:
    """One handover, with both sides of it named."""

    day: date
    egg_lot: str
    rearing_lot: str
    container: str
    fish: Decimal
    mean_weight: Quantity
    ponded_by: str

    @property
    def biomass(self) -> Quantity:
        return Quantity(self.fish * self.mean_weight.to("kg").amount, "kg")


def pond_lot(
    egg_lot: EggLot,
    container: Container,
    ledger: Ledger,
    day: object,
    fish: Number,
    mean_weight: Quantity,
    ponded_by: str,
    *,
    rearing_code: LotCode | None = None,
) -> tuple[RearingLot, Ponding]:
    """Turn a hatched egg lot into a rearing lot in a container.

    The count that crosses is the count somebody actually put in the raceway,
    which is allowed to be fewer than the egg lot was carrying and is never
    allowed to be more.
    """

    if egg_lot.stage is not EggStage.HATCHED:
        raise StateError(f"egg lot {egg_lot.code} is {egg_lot.stage.value} and cannot be ponded")
    container.check_available()
    count = require_positive(fish, field="fish")
    if count > egg_lot.count:
        raise ValidationError(
            f"{count} fish is more than the {egg_lot.count} the lot was carrying", field="fish"
        )
    require_positive(mean_weight.to("g").amount, field="mean_weight")
    when = parse_date(day)
    if when < egg_lot.spawned_on:
        raise ValidationError("that is before the eggs were taken", field="day")
    if not ponded_by.strip():
        raise ValidationError("a ponding needs whoever did it", field="ponded_by")
    code = rearing_code or egg_lot.code
    rearing = RearingLot(
        code=code,
        container=container.code,
        ponded_on=when,
        population=count,
        mean_weight=mean_weight,
        origin_egg_lot=str(egg_lot.code),
    )
    ledger.record(
        LedgerEntry(
            day=when,
            lot=str(code),
            kind=EntryKind.PONDED,
            count=count,
            entered_by=ponded_by.strip(),
            counterparty=container.code,
        )
    )
    egg_lot.advance(EggStage.PONDED)
    egg_lot.unit = container.code
    return rearing, Ponding(
        day=when,
        egg_lot=str(egg_lot.code),
        rearing_lot=str(code),
        container=container.code,
        fish=count,
        mean_weight=mean_weight,
        ponded_by=ponded_by.strip(),
    )


def ponding_loss(egg_lot: EggLot, ponding: Ponding) -> Decimal:
    """The fish the egg lot was carrying that never made it into the raceway."""

    lost = egg_lot.green_count - egg_lot.lost - ponding.fish
    return lost if lost > 0 else Decimal(0)


def check_container_free(container: Container, occupants: list[RearingLot]) -> None:
    """Refuse ponding into a unit that already has a different lot in it.

    Two lots in one raceway is a thing stations do, and it is also how a lot
    loses its identity. So it is allowed only when somebody says so explicitly,
    and this is the check that makes them.
    """

    live = [lot for lot in occupants if not lot.state.is_closed]
    if live:
        raise PolicyError(f"{container.code} already holds {live[0].code}", rule="ponding.occupied")
