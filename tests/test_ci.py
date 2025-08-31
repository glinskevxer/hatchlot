"""What CI runs is part of the repository, so it is checked like anything else.

A workflow that silently stops running the tests looks exactly like a workflow
that runs them and passes. These are cheap assertions against that.
"""

from pathlib import Path

import pytest

import hatchlot

ROOT = Path(hatchlot.__file__).parent.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE = ROOT / "scripts" / "smoke.sh"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_workflow_is_there():
    assert WORKFLOW.exists()


@pytest.mark.parametrize("job", ["lint:", "types:", "tests:", "smoke:", "build:"])
def test_every_job_is_declared(job):
    assert job in workflow_text()


def test_the_tests_job_still_runs_the_tests_with_a_coverage_gate():
    text = workflow_text()
    assert "pytest -q" in text
    assert "--cov-fail-under=90" in text


def test_the_lint_job_runs_both_halves_of_ruff():
    text = workflow_text()
    assert "ruff check ." in text
    assert "ruff format --check ." in text


def test_the_types_job_runs_mypy():
    assert "run: mypy" in workflow_text()


def test_the_workflow_runs_on_the_python_the_package_asks_for():
    text = workflow_text()
    assert 'python-version: "3.12"' in text
    assert 'requires-python = ">=3.12"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_smoke_script_is_there_and_is_executable():
    assert SMOKE.exists()
    assert SMOKE.stat().st_mode & 0o111


def test_the_smoke_script_stops_on_the_first_failure():
    text = SMOKE.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_the_smoke_script_covers_the_commands_a_station_starts_with():
    text = SMOKE.read_text(encoding="utf-8")
    for command in (
        "station init",
        "station add-unit",
        "lot pond",
        "feed record",
        "report production",
        "doctor",
    ):
        assert command in text


def test_the_smoke_script_cleans_up_after_itself():
    assert "trap" in SMOKE.read_text(encoding="utf-8")
