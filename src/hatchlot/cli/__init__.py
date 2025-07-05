"""The command line, which is the only interface this package has."""

from . import station  # noqa: F401  (registers the station commands)
from .main import main

__all__ = ["main"]
