"""The station profile: the handful of settings every other rule reads.

Two stations running the same species will not agree on the units they report
in, the month their brood year starts, or how far over a loading limit they let
a raceway sit before somebody has to sign for it. None of that belongs in the
engine, so it lives in a profile that travels with the database.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from .errors import ValidationError
from .identifiers import normalise_code
from .numeric import require_positive, require_range, to_decimal
from .units import System


@dataclass(frozen=True, slots=True)
class StationProfile:
    """Everything a station decides for itself.

    `elevation_m` is here rather than on a water source because the barometric
    pressure it implies is a property of the site, and every oxygen saturation
    in the database is worked out against it.
    """

    code: str
    name: str
    system: System = System.US
    brood_start_month: int = 7
    elevation_m: Decimal = Decimal(0)
    loading_tolerance: Decimal = Decimal("0.05")
    inventory_tolerance: Decimal = Decimal("0.02")
    mortality_alert: Decimal = Decimal("0.5")
    report_places: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="station"))
        if not self.name.strip():
            raise ValidationError("a station needs a name", field="name")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.system, System):
            raise ValidationError(f"{self.system!r} is not a unit system", field="system")
        if not 1 <= self.brood_start_month <= 12:
            raise ValidationError(
                f"{self.brood_start_month} is not a month", field="brood_start_month"
            )
        object.__setattr__(
            self, "elevation_m", require_range(self.elevation_m, -500, 4500, field="elevation_m")
        )
        object.__setattr__(
            self,
            "loading_tolerance",
            require_range(self.loading_tolerance, 0, "0.5", field="loading_tolerance"),
        )
        object.__setattr__(
            self,
            "inventory_tolerance",
            require_range(self.inventory_tolerance, 0, "0.5", field="inventory_tolerance"),
        )
        object.__setattr__(
            self, "mortality_alert", require_positive(self.mortality_alert, field="mortality_alert")
        )
        if not 0 <= self.report_places <= 6:
            raise ValidationError(
                f"{self.report_places} decimal places is not a report", field="report_places"
            )

    @property
    def is_metric(self) -> bool:
        return self.system is System.METRIC

    def with_system(self, system: System) -> StationProfile:
        """The same station reporting in the other unit system."""

        return replace(self, system=system)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "system": self.system.value,
            "brood_start_month": self.brood_start_month,
            "elevation_m": str(self.elevation_m),
            "loading_tolerance": str(self.loading_tolerance),
            "inventory_tolerance": str(self.inventory_tolerance),
            "mortality_alert": str(self.mortality_alert),
            "report_places": self.report_places,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StationProfile:
        """Rebuild a profile from storage, refusing an unknown setting.

        Refusing rather than ignoring is deliberate. A typo in a settings file
        that silently keeps the default is a rule nobody notices is off.
        """

        known = {
            "code",
            "name",
            "system",
            "brood_start_month",
            "elevation_m",
            "loading_tolerance",
            "inventory_tolerance",
            "mortality_alert",
            "report_places",
        }
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValidationError(f"unknown settings: {', '.join(unknown)}", field="profile")
        for required in ("code", "name"):
            if required not in raw:
                raise ValidationError(f"a profile needs {required}", field=required)
        system_value = raw.get("system", System.US.value)
        try:
            system = system_value if isinstance(system_value, System) else System(system_value)
        except ValueError:
            raise ValidationError(
                f"{system_value!r} is not a unit system", field="system"
            ) from None
        return cls(
            code=str(raw["code"]),
            name=str(raw["name"]),
            system=system,
            brood_start_month=int(raw.get("brood_start_month", 7)),
            elevation_m=to_decimal(raw.get("elevation_m", 0), field="elevation_m"),
            loading_tolerance=to_decimal(raw.get("loading_tolerance", "0.05")),
            inventory_tolerance=to_decimal(raw.get("inventory_tolerance", "0.02")),
            mortality_alert=to_decimal(raw.get("mortality_alert", "0.5")),
            report_places=int(raw.get("report_places", 2)),
        )


DEFAULT_PROFILE = StationProfile(code="MAIN", name="main hatchery")
