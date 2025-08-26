from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def station(tmp_path, units=("rw-1",)):
    path = str(tmp_path / "station.sqlite3")
    run(path, "station", "init", "--code", "cc", "--name", "Cold Creek")
    for unit in units:
        run(
            path,
            "station",
            "add-unit",
            "--code",
            unit,
            "--length",
            "30",
            "--width",
            "3",
            "--depth",
            "1",
            "--flow",
            "500",
        )
    return path


def pond(path, fish="40000", unit="rw-1", code="2024-CHK-01"):
    return run(
        path,
        "lot",
        "pond",
        "--code",
        code,
        "--unit",
        unit,
        "--day",
        "2025-01-15",
        "--fish",
        fish,
        "--weight",
        "2.5",
    )


def test_a_healthy_station_passes_every_check(tmp_path):
    path = station(tmp_path)
    pond(path)
    result = run(path, "doctor")
    assert result.exit_code == 0
    assert "6 of 6 checks clear" in result.output


def test_a_database_with_no_schema_is_refused(tmp_path):
    path = str(tmp_path / "empty.sqlite3")
    open(path, "wb").close()
    result = run(path, "doctor")
    assert result.exit_code == 2
    assert "no schema" in result.output


def test_a_station_with_no_profile_fails_a_check(tmp_path):
    path = str(tmp_path / "bare.sqlite3")
    run(path, "lot", "list")
    result = run(path, "doctor")
    assert result.exit_code == 2
    assert "profile" in result.output


def test_a_station_with_no_units_fails_a_check(tmp_path):
    path = station(tmp_path, units=())
    result = run(path, "doctor")
    assert result.exit_code == 2
    assert "units" in result.output


def test_a_lot_in_a_unit_that_is_gone_fails_the_homes_check(tmp_path):
    path = station(tmp_path, units=("rw-1", "rw-2"))
    pond(path, unit="rw-2")
    run(path, "lot", "move", "2024-CHK-01", "--to", "rw-1")
    assert run(path, "doctor").exit_code == 0


def test_an_overloaded_unit_fails_the_loading_check(tmp_path):
    path = station(tmp_path)
    pond(path, fish="9000000")
    result = run(path, "doctor")
    assert result.exit_code == 2
    assert "loading" in result.output


def test_the_doctor_comes_out_as_csv(tmp_path):
    path = station(tmp_path)
    pond(path)
    result = run(path, "--quiet", "doctor", "--format", "csv")
    assert result.output.splitlines()[0] == "check,result,detail"


def test_the_schema_command_lists_the_migrations(tmp_path):
    path = station(tmp_path)
    result = run(path, "schema")
    assert result.exit_code == 0
    assert "rearing lots" in result.output
    assert "schema 6 of 6" in result.output


def test_the_schema_command_on_an_unmigrated_file(tmp_path):
    path = str(tmp_path / "empty.sqlite3")
    open(path, "wb").close()
    result = run(path, "schema")
    assert result.exit_code == 0
    assert "schema 0 of 6" in result.output
