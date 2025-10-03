"""The command line, which is the only interface this package has."""

from . import (  # noqa: F401  (registering the command groups)
    calc,
    distribute,
    doctor,
    feeding,
    health,
    importing,
    incubation,
    lots,
    plan,
    report,
    station,
    water,
)
from .main import main

__all__ = ["main"]
