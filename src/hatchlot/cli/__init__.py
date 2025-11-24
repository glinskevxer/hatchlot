"""The command line, which is the only interface this package has."""

from . import (  # noqa: F401  (registering the command groups)
    brood,
    calc,
    commands,
    distribute,
    doctor,
    feeding,
    health,
    importing,
    incubation,
    lots,
    mark,
    permit,
    plan,
    report,
    rules,
    station,
    today,
    water,
)
from .main import main

__all__ = ["main"]
