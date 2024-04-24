"""The codes a hatchery writes on a tag, a tray and a truck manifest.

Every register in this package is keyed by a short code somebody wrote by hand,
which means the same lot arrives as `24-chk-01`, `24 CHK 01` and `24CHK01`.
Normalisation happens once, here, and every repository stores the normal form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ValidationError

_SEPARATORS = re.compile(r"[\s_./]+")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,23}$")
_SPECIES = re.compile(r"^[A-Z]{3}$")


def normalise_code(raw: str, *, field: str = "code") -> str:
    """Upper case, separators collapsed to a single hyphen, edges trimmed.

    This is the only place a key is cleaned up. A repository that cleans its own
    keys is a repository that disagrees with the next one.
    """

    if not isinstance(raw, str):
        raise ValidationError(f"{type(raw).__name__} is not a code", field=field)
    text = _SEPARATORS.sub("-", raw.strip().upper())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not text:
        raise ValidationError("code is empty", field=field)
    if not _CODE.match(text):
        raise ValidationError(f"{raw!r} is not a usable code", field=field)
    return text


def normalise_species(raw: str, *, field: str = "species") -> str:
    """The three letter species code the agency's forms use, such as CHK or RBT."""

    text = normalise_code(raw, field=field)
    if not _SPECIES.match(text):
        raise ValidationError(f"species code must be three letters, got {raw!r}", field=field)
    return text


def brood_year(raw: object, *, field: str = "brood_year") -> int:
    """A four digit brood year, the first half of every lot code."""

    try:
        year = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{raw!r} is not a year", field=field) from None
    if not 1900 <= year <= 2999:
        raise ValidationError(f"{year} is not a plausible brood year", field=field)
    return year


@dataclass(frozen=True, slots=True, order=True)
class LotCode:
    """`2024-CHK-01`: brood year, species, and the sequence within that year.

    Ordering is by the parts rather than the text, so lot 2 sorts before lot 10.
    """

    year: int
    species: str
    sequence: int

    def __init__(self, year: object, species: str, sequence: object) -> None:
        object.__setattr__(self, "year", brood_year(year))
        object.__setattr__(self, "species", normalise_species(species))
        try:
            number = int(str(sequence).strip())
        except (TypeError, ValueError):
            raise ValidationError(f"{sequence!r} is not a sequence", field="sequence") from None
        if not 1 <= number <= 999:
            raise ValidationError(f"sequence {number} is out of range", field="sequence")
        object.__setattr__(self, "sequence", number)

    def __str__(self) -> str:
        return f"{self.year}-{self.species}-{self.sequence:02d}"

    @classmethod
    def parse(cls, text: str) -> LotCode:
        parts = normalise_code(text, field="lot").split("-")
        if len(parts) != 3:
            raise ValidationError(f"{text!r} is not a lot code", field="lot")
        return cls(parts[0], parts[1], parts[2])

    def successor(self) -> LotCode:
        """The next lot in the same brood year and species."""

        return LotCode(self.year, self.species, self.sequence + 1)


def split_suffix(code: str, suffix: str) -> str:
    """Build the code of a lot split off an existing one: `2024-CHK-01A`."""

    base = normalise_code(code, field="lot")
    tail = normalise_code(suffix, field="suffix")
    if len(tail) > 3:
        raise ValidationError("a split suffix is at most three characters", field="suffix")
    return f"{base}{tail}"


def is_split_of(child: str, parent: str) -> bool:
    """Whether one code was built from another by :func:`split_suffix`."""

    child_code = normalise_code(child, field="lot")
    parent_code = normalise_code(parent, field="lot")
    return child_code != parent_code and child_code.startswith(parent_code)
