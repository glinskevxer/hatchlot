from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, "--quiet", *args])


def bare(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def station(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    CliRunner().invoke(
        main, ["--database", path, "station", "init", "--code", "cc", "--name", "Cold Creek"]
    )
    CliRunner().invoke(
        main,
        [
            "--database",
            path,
            "station",
            "add-unit",
            "--code",
            "rw-1",
            "--length",
            "30",
            "--width",
            "3",
            "--depth",
            "1",
            "--flow",
            "500",
        ],
    )
    CliRunner().invoke(
        main,
        [
            "--database",
            path,
            "lot",
            "pond",
            "--code",
            "2024-CHK-01",
            "--unit",
            "rw-1",
            "--day",
            "2025-01-15",
            "--fish",
            "40000",
            "--weight",
            "2.5",
        ],
    )
    return path


def test_a_size_projection_says_what_it_assumed():
    result = bare(
        "plan",
        "size",
        "--weight",
        "1",
        "--water",
        "10",
        "--from",
        "2025-01-01",
        "--to",
        "2025-04-10",
    )
    assert result.exit_code == 0
    assert "assumed water" in result.output
    assert "end weight" in result.output


def test_a_size_projection_can_be_checked_against_a_target():
    result = bare(
        "plan",
        "size",
        "--weight",
        "1",
        "--water",
        "10",
        "--from",
        "2025-01-01",
        "--to",
        "2025-04-10",
        "--target",
        "27",
    )
    assert "meets target" in result.output
    assert "yes" in result.output


def test_a_target_the_fish_will_not_reach_says_no():
    result = bare(
        "plan",
        "size",
        "--weight",
        "1",
        "--water",
        "10",
        "--from",
        "2025-01-01",
        "--to",
        "2025-02-01",
        "--target",
        "27",
    )
    assert "no" in result.output


def test_a_backwards_projection_is_refused():
    result = bare(
        "plan",
        "size",
        "--weight",
        "1",
        "--water",
        "10",
        "--from",
        "2025-04-01",
        "--to",
        "2025-01-01",
    )
    assert result.exit_code == 2


def test_a_date_projection_answers_with_a_day():
    result = bare(
        "plan",
        "date",
        "--weight",
        "1",
        "--target",
        "27",
        "--water",
        "10",
        "--from",
        "2025-01-01",
    )
    assert result.exit_code == 0
    assert "2025-04-11" in result.output


def test_a_target_no_bigger_than_the_start_is_refused():
    result = bare(
        "plan",
        "date",
        "--weight",
        "27",
        "--target",
        "27",
        "--water",
        "10",
        "--from",
        "2025-01-01",
    )
    assert result.exit_code == 2


def test_a_coefficient_is_fitted_from_two_samples():
    result = bare("plan", "fit", "--start-weight", "1", "--end-weight", "27", "--units", "1000")
    assert result.exit_code == 0
    assert "coefficient  2.00" in result.output


def test_fitting_on_a_lot_that_did_not_grow_is_refused():
    result = bare("plan", "fit", "--start-weight", "10", "--end-weight", "10", "--units", "1000")
    assert result.exit_code == 2


def test_a_lot_in_the_database_projects_off_its_own_weight(tmp_path):
    path = station(tmp_path)
    result = run(path, "plan", "lot", "2024-CHK-01", "--to", "2025-06-01", "--water", "10")
    assert result.exit_code == 0
    assert "2024-CHK-01" in result.output
    assert "biomass then" in result.output


def test_projecting_a_lot_that_is_not_there_is_refused(tmp_path):
    path = station(tmp_path)
    result = run(path, "plan", "lot", "2024-CHK-09", "--to", "2025-06-01", "--water", "10")
    assert result.exit_code == 2


def test_the_plan_group_lists_its_commands():
    result = bare("plan", "--help")
    assert "size" in result.output
    assert "fit" in result.output
