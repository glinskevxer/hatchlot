"""Biosecurity zones, and which movements between them are allowed.

A station is divided into zones by how clean the water and the stock in them are
meant to be. Fish, equipment and people all move between zones, and the rule is
the same for all three: downhill is free, uphill needs something done first.

Downhill and uphill are decided by rank, but rank alone is not the whole rule.
A lot with an open health case does not move at all, and a zone fed on reused
water cannot be the source of a movement into a zone fed on first use water even
though the ranks would allow it. Those two exceptions are the reason this is a
module rather than a comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_non_negative
from ..registry import CodeRegistry


class ZoneClass(Enum):
    """How clean a zone is meant to be, cleanest first."""

    ISOLATION = "isolation"
    QUARANTINE = "quarantine"
    PRODUCTION = "production"
    NURSERY = "nursery"
    BROODSTOCK = "broodstock"

    @property
    def rank(self) -> int:
        """Higher is cleaner. A movement to a higher rank is uphill."""

        return {
            "isolation": 0,
            "quarantine": 1,
            "production": 2,
            "nursery": 3,
            "broodstock": 4,
        }[self.value]

    @property
    def is_restricted(self) -> bool:
        return self in {ZoneClass.ISOLATION, ZoneClass.QUARANTINE}


@dataclass
class Zone:
    """One biosecurity zone on the station."""

    code: str
    zone_class: ZoneClass
    water_source: str = ""
    reuse_share: Decimal = Decimal(0)
    shared_equipment: bool = False

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="zone")
        if not isinstance(self.zone_class, ZoneClass):
            raise ValidationError(f"{self.zone_class!r} is not a zone class", field="zone_class")
        if self.water_source:
            self.water_source = normalise_code(self.water_source, field="water_source")
        self.reuse_share = require_non_negative(self.reuse_share, field="reuse_share")
        if self.reuse_share > 1:
            raise ValidationError("a reuse share over one is not a share", field="reuse_share")

    @property
    def is_first_use(self) -> bool:
        return self.reuse_share == 0


class ZoneMap(CodeRegistry[Zone]):
    """Every zone, and the rules for moving between them."""

    def __init__(self) -> None:
        super().__init__("zone", lambda zone: zone.code)

    def direction(self, origin: str, destination: str) -> str:
        """Whether a movement runs uphill, downhill or across."""

        source = self.get(origin)
        target = self.get(destination)
        if target.zone_class.rank > source.zone_class.rank:
            return "uphill"
        if target.zone_class.rank < source.zone_class.rank:
            return "downhill"
        return "across"

    def check_movement(
        self,
        origin: str,
        destination: str,
        *,
        lot_has_open_case: bool = False,
        disinfected: bool = False,
    ) -> None:
        """Refuse a movement the biosecurity plan does not allow.

        The checks run in the order the plan is written: the health of the stock
        first, then the water, then the ranks. Each refusal names its own rule so
        the person told no knows which one to argue with.
        """

        source = self.get(origin)
        target = self.get(destination)
        if lot_has_open_case:
            raise PolicyError(
                f"the lot has an open case and cannot leave {source.code}",
                rule="biosecurity.open_case",
            )
        if source.code == target.code:
            return
        if not source.is_first_use and target.is_first_use:
            raise PolicyError(
                f"{source.code} is on reused water and {target.code} is not",
                rule="biosecurity.water",
            )
        if source.zone_class.is_restricted and not target.zone_class.is_restricted:
            raise PolicyError(
                f"{source.code} is {source.zone_class.value} and nothing leaves it",
                rule="biosecurity.restricted",
            )
        if self.direction(origin, destination) == "uphill" and not disinfected:
            raise PolicyError(
                f"moving from {source.code} to {target.code} is uphill and needs "
                "equipment disinfected first",
                rule="biosecurity.uphill",
            )

    def may_move(
        self,
        origin: str,
        destination: str,
        *,
        lot_has_open_case: bool = False,
        disinfected: bool = False,
    ) -> bool:
        """The same question as a yes or no, for a report rather than a refusal."""

        try:
            self.check_movement(
                origin,
                destination,
                lot_has_open_case=lot_has_open_case,
                disinfected=disinfected,
            )
        except PolicyError:
            return False
        return True

    def destinations_from(self, origin: str, *, disinfected: bool = False) -> tuple[str, ...]:
        """Every zone a lot in this one could go to today."""

        return tuple(
            zone.code
            for zone in self.all()
            if zone.code != normalise_code(origin, field="zone")
            and self.may_move(origin, zone.code, disinfected=disinfected)
        )

    def restricted_zones(self) -> tuple[Zone, ...]:
        return self.where(lambda zone: zone.zone_class.is_restricted)

    def on_source(self, source: str) -> tuple[Zone, ...]:
        code = normalise_code(source, field="water_source")
        return self.where(lambda zone: zone.water_source == code)


def equipment_rule(origin: Zone, destination: Zone) -> str:
    """What has to happen to a net between two zones."""

    if origin.code == destination.code:
        return "nothing"
    if origin.zone_class.is_restricted:
        return "dedicated"
    if destination.zone_class.rank > origin.zone_class.rank:
        return "disinfect"
    return "rinse"


def contact_score(map_: ZoneMap, code: str) -> Decimal:
    """A blunt exposure score for a zone: how many zones can reach it.

    Not a risk model. It is the number that says which zone to look at first when
    something turns up somewhere it should not have.
    """

    target = map_.get(code)
    reachable = [
        zone
        for zone in map_.all()
        if zone.code != target.code and map_.may_move(zone.code, target.code, disinfected=True)
    ]
    return require_non_negative(len(reachable), field="contact")


def zone_of(map_: ZoneMap, container: str, layout: dict[str, str]) -> Zone:
    """Which zone a container sits in, from the station's layout."""

    code = normalise_code(container, field="container")
    if code not in layout:
        raise ValidationError(f"{code} is not on the zone layout", field="container")
    return map_.get(layout[code])


def reuse_downstream(map_: ZoneMap, threshold: Number = "0.5") -> tuple[Zone, ...]:
    """Zones carrying more reused water than the station is comfortable with."""

    limit = require_non_negative(threshold, field="threshold")
    return map_.where(lambda zone: zone.reuse_share > limit)
