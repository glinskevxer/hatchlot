"""The command line, which is the only interface this package has."""

from . import calc, lots, station  # noqa: F401  (registering the command groups)
from .main import main

__all__ = ["main"]
