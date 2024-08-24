"""The units fish are reared in, and what their shape decides.

A trough, a circular tank and a hundred foot raceway are the same record with
different numbers in it, and almost everything downstream is a function of those
numbers. Volume sets the density limit. Flow against volume sets the exchange
rate, which is how fast the water is replaced and therefore how quickly a
problem clears. Depth sets how much gas supersaturation the fish can escape.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from ..registry import CodeRegistry


class ContainerKind(Enum):
    """What kind of unit it is, which decides how it is worked."""

    TROUGH = "trough"
    TANK = "tank"
    CIRCULAR = "circular"
    RACEWAY = "raceway"
    POND = "pond"

    @property
    def is_outdoor(self) -> bool:
        return self in {ContainerKind.RACEWAY, ContainerKind.POND}

    @property
    def is_self_cleaning(self) -> bool:
        """Circulars carry their own waste to the centre drain."""

        return self is ContainerKind.CIRCULAR


@dataclass
class Container:
    """One rearing unit and the water on it."""

    code: str
    kind: ContainerKind
    length: Quantity
    width: Quantity
    depth: Quantity
    flow: Quantity
    water_source: str = ""
    out_of_service: bool = False

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="container")
        if not isinstance(self.kind, ContainerKind):
            raise ValidationError(f"{self.kind!r} is not a container kind", field="kind")
        for name in ("length", "width", "depth"):
            require_positive(getattr(self, name).to("m").amount, field=name)
        require_positive(self.flow.to("Lpm").amount, field="flow")
        if self.water_source:
            self.water_source = normalise_code(self.water_source, field="water_source")

    @property
    def volume(self) -> Quantity:
        """The water it holds, worked out from its dimensions."""

        cubic_metres = (
            self.length.to("m").amount * self.width.to("m").amount * self.depth.to("m").amount
        )
        return Quantity(cubic_metres, "m3")

    @property
    def surface_area(self) -> Quantity:
        return Quantity(self.length.to("m").amount * self.width.to("m").amount * Decimal(1), "m3")

    @property
    def exchange_rate(self) -> Decimal:
        """How many times an hour the water in the unit is replaced."""

        litres = self.volume.to("L").amount
        per_hour = self.flow.to("Lpm").amount * Decimal(60)
        return safe_divide(per_hour, litres, field="volume")

    @property
    def turnover_minutes(self) -> Decimal:
        """How long one complete change of water takes."""

        return safe_divide(self.volume.to("L").amount, self.flow.to("Lpm").amount, field="flow")

    def is_available(self) -> bool:
        return not self.out_of_service

    def take_out_of_service(self, reason: str) -> None:
        if not reason.strip():
            raise ValidationError("taking a unit off needs a reason", field="reason")
        self.out_of_service = True

    def return_to_service(self) -> None:
        self.out_of_service = False

    def check_available(self) -> None:
        if self.out_of_service:
            raise PolicyError(f"{self.code} is out of service", rule="container.out_of_service")

    def with_flow(self, flow: Quantity) -> Container:
        """The same unit on a different flow, which is what a valve does."""

        require_positive(flow.to("Lpm").amount, field="flow")
        return Container(
            code=self.code,
            kind=self.kind,
            length=self.length,
            width=self.width,
            depth=self.depth,
            flow=flow,
            water_source=self.water_source,
            out_of_service=self.out_of_service,
        )


class ContainerRegister(CodeRegistry[Container]):
    """Every rearing unit on the station."""

    def __init__(self) -> None:
        super().__init__("container", lambda container: container.code)

    def of_kind(self, kind: ContainerKind) -> tuple[Container, ...]:
        return self.where(lambda container: container.kind is kind)

    def available(self) -> tuple[Container, ...]:
        return self.where(lambda container: container.is_available())

    def on_source(self, source: str) -> tuple[Container, ...]:
        code = normalise_code(source, field="water_source")
        return self.where(lambda container: container.water_source == code)

    def total_volume(self, symbol: str = "m3") -> Quantity:
        total = Quantity(0, symbol)
        for container in self.all():
            total = total + container.volume
        return total

    def total_flow(self, symbol: str = "Lpm") -> Quantity:
        total = Quantity(0, symbol)
        for container in self.available():
            total = total + container.flow
        return total

    def slowest(self) -> Container | None:
        """The unit with the longest turnover, which is the one that worries."""

        units = self.all()
        if not units:
            return None
        return max(units, key=lambda container: container.turnover_minutes)


def exchange_ratio(container: Container, target_minutes: Number) -> Decimal:
    """How much more flow a unit needs to hit a target turnover."""

    target = require_positive(target_minutes, field="target_minutes")
    return safe_divide(container.turnover_minutes, target, field="target_minutes")
