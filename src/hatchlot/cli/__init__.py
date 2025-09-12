"""The command line, which is the only interface this package has."""

from . import (  # noqa: F401  (registering the command groups)
    calc,
    doctor,
    feeding,
    health,
    importing,
    lots,
    plan,
    report,
    station,
    water,
)
from .main import main

__all__ = ["main"]
