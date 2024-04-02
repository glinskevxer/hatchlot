"""The exception hierarchy.

Every error the package raises deliberately is a :class:`HatchlotError`. Anything
else escaping is a bug, and the CLI treats it that way: a `HatchlotError` prints
one line and exits 2, everything else prints a traceback.
"""

from __future__ import annotations


class HatchlotError(Exception):
    """Base for every error this package raises on purpose."""


class ValidationError(HatchlotError):
    """A value did not survive its own constructor.

    `field` names the thing that was wrong so a caller can point at the input
    rather than at the record.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field

    def __str__(self) -> str:
        base = super().__str__()
        return f"{self.field}: {base}" if self.field else base


class UnitError(ValidationError):
    """A quantity was handed a unit it does not speak."""


class ConversionError(HatchlotError):
    """Two quantities could not be brought into the same unit."""


class NotFoundError(HatchlotError):
    """A record was asked for by key and is not there."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"no {kind} with key {key!r}")
        self.kind = kind
        self.key = key


class DuplicateError(HatchlotError):
    """A record was stored under a key that is already taken."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"{kind} {key!r} already exists")
        self.kind = kind
        self.key = key


class StateError(HatchlotError):
    """An operation is legal in general and illegal in the state it was asked in."""


class PolicyError(HatchlotError):
    """A station rule refused the operation.

    Distinct from :class:`StateError` on purpose. A state error means the record
    is in the wrong shape; a policy error means the record is fine and the rule
    says no anyway, which is the answer an operator has to be able to appeal.
    """

    def __init__(self, message: str, *, rule: str) -> None:
        super().__init__(message)
        self.rule = rule

    def __str__(self) -> str:
        return f"[{self.rule}] {super().__str__()}"
