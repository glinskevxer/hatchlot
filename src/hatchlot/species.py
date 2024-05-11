"""The species table, and the constants that come attached to a species.

Every rule downstream is really a species rule. Chinook eye up on a different
count of thermal units than steelhead, a raceway will carry more brook trout
than coho, and the temperature that is comfortable for one is lethal for
another. Rather than scatter those numbers through the engine, they live here
and everything else asks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .errors import NotFoundError, ValidationError
from .identifiers import normalise_species


@dataclass(frozen=True, slots=True)
class Species:
    """One species and the constants a station runs it on.

    Thermal units are Celsius degree days above the species zero point, which is
    why the zero point travels with them. The density and flow index limits are
    the loading a station is allowed to carry per inch of fish, in the customary
    units those indices are always quoted in.
    """

    code: str
    common_name: str
    zero_point_c: Decimal
    eye_up_units: Decimal
    hatch_units: Decimal
    swim_up_units: Decimal
    density_index_limit: Decimal
    flow_index_limit: Decimal
    rearing_low_c: Decimal
    rearing_high_c: Decimal
    lethal_high_c: Decimal
    condition_factor: Decimal
    anadromous: bool

    def development_fraction(self, units: Decimal | int) -> Decimal:
        """How far through incubation a lot is, as a fraction of hatch.

        Above hatch this keeps counting, because a lot held past hatch is a real
        situation and clamping it would hide it.
        """

        return Decimal(units) / self.hatch_units

    def is_within_rearing_band(self, celsius: Decimal) -> bool:
        return self.rearing_low_c <= celsius <= self.rearing_high_c


def _s(
    code: str,
    common_name: str,
    zero: str,
    eye: str,
    hatch: str,
    swim: str,
    density: str,
    flow: str,
    low: str,
    high: str,
    lethal: str,
    condition: str,
    anadromous: bool,
) -> Species:
    return Species(
        code=code,
        common_name=common_name,
        zero_point_c=Decimal(zero),
        eye_up_units=Decimal(eye),
        hatch_units=Decimal(hatch),
        swim_up_units=Decimal(swim),
        density_index_limit=Decimal(density),
        flow_index_limit=Decimal(flow),
        rearing_low_c=Decimal(low),
        rearing_high_c=Decimal(high),
        lethal_high_c=Decimal(lethal),
        condition_factor=Decimal(condition),
        anadromous=anadromous,
    )


_SPECIES: dict[str, Species] = {
    s.code: s
    for s in (
        _s(
            "CHK",
            "chinook salmon",
            "0",
            "425",
            "850",
            "1300",
            "0.5",
            "1.5",
            "6",
            "14",
            "22",
            "0.00040",
            True,
        ),
        _s(
            "COH",
            "coho salmon",
            "0",
            "440",
            "880",
            "1350",
            "0.5",
            "1.5",
            "6",
            "14",
            "22",
            "0.00041",
            True,
        ),
        _s(
            "CHM",
            "chum salmon",
            "0",
            "410",
            "820",
            "1250",
            "0.45",
            "1.4",
            "5",
            "13",
            "21",
            "0.00038",
            True,
        ),
        _s(
            "STH",
            "steelhead",
            "0",
            "240",
            "500",
            "800",
            "0.6",
            "1.8",
            "7",
            "15",
            "23",
            "0.00042",
            True,
        ),
        _s(
            "RBT",
            "rainbow trout",
            "0",
            "240",
            "500",
            "800",
            "0.6",
            "1.8",
            "7",
            "16",
            "24",
            "0.00042",
            False,
        ),
        _s(
            "BKT",
            "brook trout",
            "0",
            "230",
            "480",
            "760",
            "0.55",
            "1.7",
            "5",
            "15",
            "23",
            "0.00043",
            False,
        ),
        _s(
            "BNT",
            "brown trout",
            "0",
            "250",
            "520",
            "820",
            "0.55",
            "1.7",
            "6",
            "16",
            "24",
            "0.00042",
            False,
        ),
        _s(
            "KOK",
            "kokanee",
            "0",
            "420",
            "840",
            "1290",
            "0.45",
            "1.4",
            "5",
            "13",
            "21",
            "0.00039",
            False,
        ),
        _s(
            "ATS",
            "atlantic salmon",
            "0",
            "450",
            "900",
            "1400",
            "0.5",
            "1.6",
            "6",
            "15",
            "23",
            "0.00041",
            True,
        ),
    )
}

_ALIASES = {
    "chinook": "CHK",
    "king": "CHK",
    "coho": "COH",
    "silver": "COH",
    "chum": "CHM",
    "steelhead": "STH",
    "rainbow": "RBT",
    "brook": "BKT",
    "brookie": "BKT",
    "brown": "BNT",
    "kokanee": "KOK",
    "atlantic": "ATS",
}


def species(code: str) -> Species:
    """Look a species up by its three letter code."""

    key = normalise_species(code)
    try:
        return _SPECIES[key]
    except KeyError:
        raise NotFoundError("species", key) from None


def resolve_species(text: str) -> Species:
    """Look a species up by code or by the name a crew actually says."""

    if not isinstance(text, str) or not text.strip():
        raise ValidationError("empty species", field="species")
    cleaned = text.strip().lower()
    candidates = [cleaned, cleaned.split()[0]]
    candidates += [word.rstrip("s") for word in list(candidates)]
    for word in candidates:
        if word in _ALIASES:
            return species(_ALIASES[word])
    return species(text)


def all_species() -> tuple[Species, ...]:
    """Every species in the table, in code order."""

    return tuple(_SPECIES[code] for code in sorted(_SPECIES))


def anadromous_species() -> tuple[Species, ...]:
    return tuple(s for s in all_species() if s.anadromous)
