"""One keyed register, since every part of the station wanted its own.

Water sources, takes, containers, feed lots and everything else are all the same
shape: a dictionary keyed by a normalised code, that refuses a duplicate, raises
a named not-found, and lists in code order. Writing that five times meant five
slightly different behaviours on a missing key.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

from .errors import DuplicateError, NotFoundError
from .identifiers import normalise_code

T = TypeVar("T")


class CodeRegistry(Generic[T]):
    """A register of records keyed by a code, in code order."""

    def __init__(self, kind: str, key_of: Callable[[T], str]) -> None:
        self._kind = kind
        self._key_of = key_of
        self._items: dict[str, T] = {}

    @property
    def kind(self) -> str:
        return self._kind

    def add(self, item: T) -> T:
        key = normalise_code(self._key_of(item), field=self._kind)
        if key in self._items:
            raise DuplicateError(self._kind, key)
        self._items[key] = item
        return item

    def replace(self, item: T) -> T:
        """Overwrite a record that is already there, refusing one that is not."""

        key = normalise_code(self._key_of(item), field=self._kind)
        if key not in self._items:
            raise NotFoundError(self._kind, key)
        self._items[key] = item
        return item

    def get(self, code: str) -> T:
        key = normalise_code(code, field=self._kind)
        try:
            return self._items[key]
        except KeyError:
            raise NotFoundError(self._kind, key) from None

    def find(self, code: str) -> T | None:
        """The lookup that answers None instead of raising."""

        return self._items.get(normalise_code(code, field=self._kind))

    def remove(self, code: str) -> T:
        key = normalise_code(code, field=self._kind)
        try:
            return self._items.pop(key)
        except KeyError:
            raise NotFoundError(self._kind, key) from None

    def codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def all(self) -> tuple[T, ...]:
        return tuple(self._items[code] for code in self.codes())

    def where(self, predicate: Callable[[T], bool]) -> tuple[T, ...]:
        return tuple(item for item in self.all() if predicate(item))

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self.all())

    def __contains__(self, code: object) -> bool:
        if not isinstance(code, str):
            return False
        try:
            key = normalise_code(code, field=self._kind)
        except Exception:
            return False
        return key in self._items
