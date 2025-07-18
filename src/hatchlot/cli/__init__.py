"""The command line, which is the only interface this package has."""

from . import calc, lots, station, water  # noqa: F401  (registering the groups)
from .main import main

__all__ = ["main"]
