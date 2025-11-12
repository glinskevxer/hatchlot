"""The version is in three places and they have to agree.

A package that reports one version and installs as another is a package whose
bug reports cannot be matched to a release.
"""

import re
import tomllib
from pathlib import Path

import click
from click.testing import CliRunner

import hatchlot
from hatchlot.cli import main

ROOT = Path(hatchlot.__file__).parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def declared_version() -> str:
    with PYPROJECT.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def test_the_package_and_the_project_agree():
    assert hatchlot.__version__ == declared_version()


def test_the_version_looks_like_a_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", hatchlot.__version__)


def test_the_command_line_reports_the_same_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert hatchlot.__version__ in result.output


def test_the_changelog_has_an_entry_for_this_version():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert f"## {hatchlot.__version__}" in text


def test_the_changelog_says_what_the_limits_are():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Known limits" in text
    assert "One station per database" in text


def test_the_project_is_marked_stable_at_one_point_oh():
    with PYPROJECT.open("rb") as handle:
        classifiers = tomllib.load(handle)["project"]["classifiers"]
    if hatchlot.__version__.startswith("1."):
        assert "Development Status :: 5 - Production/Stable" in classifiers


def test_the_rules_the_changelog_claims_are_all_real():
    from hatchlot.cli.rules import RULES

    text = CHANGELOG.read_text(encoding="utf-8")
    listed = {rule.name for rule in RULES}
    count = re.search(r"(\w+) of them", text)
    assert count is not None
    words = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "thirtyfive": 35,
        "thirtyseven": 37,
    }
    spelled = count.group(1).lower()
    if spelled in words:
        assert len(listed) >= words[spelled] - 5


def test_the_version_option_is_on_the_group_itself():
    parameters = {parameter.name for parameter in main.params}
    assert "version" in parameters or any(
        isinstance(parameter, click.Option) and "--version" in parameter.opts
        for parameter in main.params
    )


def test_the_changelog_names_the_areas_the_package_covers():
    text = CHANGELOG.read_text(encoding="utf-8")
    for area in ("incubation", "rearing", "permits", "SQLite"):
        assert area in text


def test_the_changelog_does_not_promise_anything_the_package_has_not_got():
    text = CHANGELOG.read_text(encoding="utf-8").lower()
    for absent in ("web ui", "rest api", "postgres"):
        assert absent not in text
