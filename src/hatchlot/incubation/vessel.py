"""The hardware eggs sit in, and the rules about filling it.

Trays stack, and water that has passed the tray above arrives at the tray below
already used. So a stack has a limit on how many of its positions can be loaded
at once, and that limit is a property of the stack rather than of any tray in
it. Jars are different again: they hold eggs by volume, so their capacity moves
with the size of the egg.

Everything here refuses to be overfilled. An incubation room that is quietly
over capacity looks fine until the day the flow drops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from ..errors import DuplicateError, PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from ..registry import CodeRegistry


class VesselKind(Enum):
    """What the eggs are sitting in."""

    TRAY = "tray"
    JAR = "jar"
    UPWELLING = "upwelling"

    @property
    def is_volumetric(self) -> bool:
        """Whether its capacity moves with the size of the egg."""

        return self in {VesselKind.JAR, VesselKind.UPWELLING}


@dataclass
class Vessel:
    """One tray, jar or upwelling box."""

    code: str
    kind: VesselKind
    flow: Quantity
    capacity_eggs: Decimal = Decimal(0)
    volume: Quantity | None = None
    stack: str = ""
    position: int = 0
    contents: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="vessel")
        if not isinstance(self.kind, VesselKind):
            raise ValidationError(f"{self.kind!r} is not a vessel kind", field="kind")
        require_positive(self.flow.to("Lpm").amount, field="flow")
        if self.stack:
            self.stack = normalise_code(self.stack, field="stack")
            if self.position < 1:
                raise ValidationError("a vessel in a stack needs a position", field="position")
        if self.kind.is_volumetric:
            if self.volume is None:
                raise ValidationError("a jar holds eggs by volume", field="volume")
            require_positive(self.volume.to("L").amount, field="volume")
        elif self.capacity_eggs <= 0:
            raise ValidationError("a tray holds a number of eggs", field="capacity_eggs")

    def capacity(self, eggs_per_litre: Number | None = None) -> Decimal:
        """How many eggs this vessel takes, given an egg size where it matters."""

        if not self.kind.is_volumetric:
            return self.capacity_eggs
        if eggs_per_litre is None:
            raise ValidationError("a jar's capacity needs an egg size", field="eggs_per_litre")
        density = require_positive(eggs_per_litre, field="eggs_per_litre")
        assert self.volume is not None
        return density * self.volume.to("L").amount

    @property
    def loaded(self) -> Decimal:
        return sum(self.contents.values(), Decimal(0))

    @property
    def is_empty(self) -> bool:
        return self.loaded == 0

    def free(self, eggs_per_litre: Number | None = None) -> Decimal:
        return self.capacity(eggs_per_litre) - self.loaded

    def load(self, lot: str, eggs: Number, eggs_per_litre: Number | None = None) -> Decimal:
        """Put eggs in, refusing an overfill."""

        code = normalise_code(lot, field="lot")
        amount = require_positive(eggs, field="eggs")
        if amount > self.free(eggs_per_litre):
            raise PolicyError(
                f"vessel {self.code} has room for {self.free(eggs_per_litre):.0f} more eggs",
                rule="incubation.overfill",
            )
        self.contents[code] = self.contents.get(code, Decimal(0)) + amount
        return self.contents[code]

    def unload(self, lot: str, eggs: Number | None = None) -> Decimal:
        """Take eggs out, all of a lot's by default."""

        code = normalise_code(lot, field="lot")
        if code not in self.contents:
            raise ValidationError(f"{code} is not in {self.code}", field="lot")
        if eggs is None:
            return self.contents.pop(code)
        amount = require_positive(eggs, field="eggs")
        if amount > self.contents[code]:
            raise ValidationError(
                f"{self.code} holds {self.contents[code]} of {code}", field="eggs"
            )
        self.contents[code] -= amount
        if self.contents[code] == 0:
            del self.contents[code]
        return amount

    def fill_share(self, eggs_per_litre: Number | None = None) -> Decimal:
        return safe_divide(self.loaded, self.capacity(eggs_per_litre), field="capacity")


class VesselRegister(CodeRegistry[Vessel]):
    """Every vessel in the incubation room."""

    def __init__(self, *, stack_limit: int = 8) -> None:
        super().__init__("vessel", lambda vessel: vessel.code)
        if stack_limit < 1:
            raise ValidationError("a stack holds at least one tray", field="stack_limit")
        self._stack_limit = stack_limit

    @property
    def stack_limit(self) -> int:
        return self._stack_limit

    def add(self, item: Vessel) -> Vessel:
        if item.stack:
            taken = [
                vessel for vessel in self.in_stack(item.stack) if vessel.position == item.position
            ]
            if taken:
                raise DuplicateError("stack position", f"{item.stack}/{item.position}")
        return super().add(item)

    def in_stack(self, stack: str) -> tuple[Vessel, ...]:
        code = normalise_code(stack, field="stack")
        return tuple(
            sorted(
                self.where(lambda vessel: vessel.stack == code),
                key=lambda vessel: vessel.position,
            )
        )

    def loaded_in_stack(self, stack: str) -> int:
        return len([vessel for vessel in self.in_stack(stack) if not vessel.is_empty])

    def check_stack(self, stack: str) -> None:
        """Refuse a stack running more loaded trays than it has water for."""

        loaded = self.loaded_in_stack(stack)
        if loaded > self._stack_limit:
            raise PolicyError(
                f"stack {normalise_code(stack)} has {loaded} trays loaded, limit is "
                f"{self._stack_limit}",
                rule="incubation.stack_limit",
            )

    def of_kind(self, kind: VesselKind) -> tuple[Vessel, ...]:
        return self.where(lambda vessel: vessel.kind is kind)

    def holding(self, lot: str) -> tuple[Vessel, ...]:
        code = normalise_code(lot, field="lot")
        return self.where(lambda vessel: code in vessel.contents)

    def eggs_of(self, lot: str) -> Decimal:
        code = normalise_code(lot, field="lot")
        return sum((vessel.contents.get(code, Decimal(0)) for vessel in self.all()), Decimal(0))

    def flow_demand(self, symbol: str = "Lpm") -> Quantity:
        total = Quantity(0, symbol)
        for vessel in self.all():
            if not vessel.is_empty:
                total = total + vessel.flow
        return total
