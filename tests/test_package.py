import importlib
import pkgutil
from pathlib import Path

import pytest

import hatchlot
from hatchlot import (
    DateRange,
    HatchlotError,
    LotCode,
    PolicyError,
    Quantity,
    Temperature,
    ValidationError,
    __version__,
    convert,
    species,
)

PACKAGE_ROOT = Path(hatchlot.__file__).parent


def test_the_version_is_readable_and_looks_like_one():
    assert __version__.count(".") == 2
    assert all(part.isdigit() for part in __version__.split("."))


def test_the_things_a_caller_needs_are_exported_from_the_root():
    assert Quantity(1, "kg").symbol == "kg"
    assert Temperature(50, "F").celsius == 10
    assert convert(1, "ft", "in") == 12
    assert species("CHK").code == "CHK"
    assert str(LotCode(2024, "CHK", 1)) == "2024-CHK-01"
    assert DateRange("2025-03-01", "2025-03-31").days == 31


def test_everything_deliberate_is_one_family_from_the_root_too():
    assert issubclass(ValidationError, HatchlotError)
    assert issubclass(PolicyError, HatchlotError)


def test_the_export_list_is_sorted_and_complete():
    assert hatchlot.__all__ == sorted(hatchlot.__all__)
    for name in hatchlot.__all__:
        assert hasattr(hatchlot, name), name


def test_the_package_ships_its_type_information():
    assert (PACKAGE_ROOT / "py.typed").exists()


def test_every_module_imports_on_its_own():
    for module in pkgutil.walk_packages([str(PACKAGE_ROOT)], prefix="hatchlot."):
        importlib.import_module(module.name)


def test_every_package_has_a_docstring():
    for module in pkgutil.walk_packages([str(PACKAGE_ROOT)], prefix="hatchlot."):
        if not module.ispkg:
            continue
        loaded = importlib.import_module(module.name)
        assert loaded.__doc__, module.name


def test_the_public_names_of_every_subpackage_resolve():
    for name in (
        "hatchlot.water",
        "hatchlot.brood",
        "hatchlot.incubation",
        "hatchlot.rearing",
        "hatchlot.feed",
        "hatchlot.health",
        "hatchlot.marking",
        "hatchlot.distribution",
        "hatchlot.permits",
        "hatchlot.ingest",
        "hatchlot.store",
        "hatchlot.reporting",
    ):
        loaded = importlib.import_module(name)
        exported = getattr(loaded, "__all__", [])
        assert exported == sorted(exported), name
        for exported_name in exported:
            assert hasattr(loaded, exported_name), f"{name}.{exported_name}"


def test_the_console_script_is_declared():
    text = (PACKAGE_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert 'hatchlot = "hatchlot.cli.main:main"' in text
    assert "Typing :: Typed" in text


@pytest.mark.parametrize("name", ["click"])
def test_the_only_runtime_dependency_is_declared(name):
    text = (PACKAGE_ROOT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{name}==' in text
