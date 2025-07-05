from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def setup_station(path):
    return run(path, "station", "init", "--code", "cold-creek", "--name", "Cold Creek")


def database(tmp_path):
    return str(tmp_path / "station.sqlite3")


def test_a_station_is_created_and_read_back(tmp_path):
    path = database(tmp_path)
    assert setup_station(path).exit_code == 0
    result = run(path, "station", "show")
    assert result.exit_code == 0
    assert "COLD-CREEK" in result.output
    assert "Cold Creek" in result.output


def test_a_station_with_an_impossible_brood_month_is_refused(tmp_path):
    result = run(
        database(tmp_path),
        "station",
        "init",
        "--code",
        "x",
        "--name",
        "X",
        "--brood-month",
        "13",
    )
    assert result.exit_code == 2
    assert "invalid" in result.output


def test_showing_a_station_that_was_never_created(tmp_path):
    result = run(database(tmp_path), "station", "show")
    assert result.exit_code == 2
    assert "not found" in result.output


def test_a_source_and_a_unit_go_on_and_come_back(tmp_path):
    path = database(tmp_path)
    setup_station(path)
    assert (
        run(
            path,
            "station",
            "add-source",
            "--code",
            "sp-1",
            "--name",
            "upper spring",
            "--flow",
            "900",
            "--minimum",
            "400",
        ).exit_code
        == 0
    )
    assert (
        run(
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
            "--source",
            "sp-1",
        ).exit_code
        == 0
    )
    units = run(path, "station", "units")
    assert "RW-1" in units.output
    assert "1 unit" in units.output
    water = run(path, "station", "water")
    assert "SP-1" in water.output
    assert "400 gpm" in water.output


def test_a_unit_on_a_source_that_is_not_there_is_refused(tmp_path):
    path = database(tmp_path)
    setup_station(path)
    result = run(
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
        "--source",
        "sp-9",
    )
    assert result.exit_code == 2


def test_a_unit_with_no_depth_is_refused(tmp_path):
    path = database(tmp_path)
    setup_station(path)
    result = run(
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
        "0",
        "--flow",
        "500",
    )
    assert result.exit_code == 2
    assert "depth" in result.output


def test_the_units_listing_can_leave_out_what_is_off(tmp_path):
    path = database(tmp_path)
    setup_station(path)
    run(
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
    )
    assert "RW-1" in run(path, "station", "units", "--available").output


def test_a_listing_comes_out_as_csv_when_asked(tmp_path):
    path = database(tmp_path)
    setup_station(path)
    run(
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
    )
    result = run(path, "--quiet", "station", "units", "--format", "csv")
    assert result.output.splitlines()[0].startswith("code,kind,volume,volume_unit")


def test_the_station_group_has_its_own_help(tmp_path):
    result = run(database(tmp_path), "station", "--help")
    assert result.exit_code == 0
    assert "add-unit" in result.output
