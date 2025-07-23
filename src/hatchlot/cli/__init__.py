"""The command line, which is the only interface this package has."""

from . import (  # noqa: F401  (registering the command groups)
    calc,
    feeding,
    lots,
    report,
    station,
    water,
)
from .main import main

__all__ = ["main"]
