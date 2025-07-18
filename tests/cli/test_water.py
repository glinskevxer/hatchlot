from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def station(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    run(path, "station", "init", "--code", "cc", "--name", "Cold Creek")
    return path


def reading(path, at="2025-03-01 06:00", unit="rw-1", temperature="10", oxygen="9", scale="C"):
    return run(
        path,
        "water",
        "record",
        "--unit",
        unit,
        "--at",
        at,
        "--temperature",
        temperature,
        "--scale",
        scale,
        "--oxygen",
        oxygen,
    )


def test_a_reading_goes_on_and_comes_back(tmp_path):
    path = station(tmp_path)
    assert reading(path).exit_code == 0
    listing = run(path, "water", "list")
    assert "RW-1" in listing.output
    assert "1 reading" in listing.output


def test_a_fahrenheit_reading_is_stored_in_celsius(tmp_path):
    path = station(tmp_path)
    reading(path, temperature="50", scale="F")
    assert "10 degC" in run(path, "water", "list").output


def test_a_negative_oxygen_reading_is_refused(tmp_path):
    path = station(tmp_path)
    assert reading(path, oxygen="-1").exit_code == 2


def test_a_reading_at_a_time_that_is_not_a_time_is_refused(tmp_path):
    path = station(tmp_path)
    assert reading(path, at="whenever").exit_code == 2


def test_recording_the_same_time_twice_replaces_the_reading(tmp_path):
    path = station(tmp_path)
    reading(path, oxygen="9")
    reading(path, oxygen="7")
    listing = run(path, "water", "list")
    assert "1 reading" in listing.output
    assert "7" in listing.output


def test_the_readings_can_be_narrowed_to_one_unit_and_one_window(tmp_path):
    path = station(tmp_path)
    reading(path, unit="rw-1", at="2025-03-01 06:00")
    reading(path, unit="rw-2", at="2025-03-02 06:00")
    reading(path, unit="rw-1", at="2025-04-01 06:00")
    assert "2 readings" in run(path, "water", "list", "--unit", "rw-1").output
    assert (
        "2 readings"
        in run(path, "water", "list", "--from", "2025-03-01", "--to", "2025-03-31").output
    )


def test_bad_readings_collapse_into_an_excursion(tmp_path):
    path = station(tmp_path)
    reading(path, at="2025-03-01 06:00", oxygen="4")
    reading(path, at="2025-03-01 12:00", oxygen="4.5")
    reading(path, at="2025-03-01 18:00", oxygen="9")
    result = run(path, "water", "excursions")
    assert "low_oxygen" in result.output
    assert "1 excursion" in result.output


def test_the_excursion_thresholds_can_be_moved(tmp_path):
    path = station(tmp_path)
    reading(path, oxygen="6.5")
    assert "0 excursions" in run(path, "water", "excursions").output
    assert "1 excursion" in run(path, "water", "excursions", "--minimum-oxygen", "7").output


def test_the_latest_reading_on_a_unit(tmp_path):
    path = station(tmp_path)
    reading(path, at="2025-03-01 06:00", oxygen="9")
    reading(path, at="2025-03-02 06:00", oxygen="8")
    result = run(path, "water", "latest", "rw-1")
    assert result.exit_code == 0
    assert "mean oxygen" in result.output
    assert "8.50" in result.output


def test_a_unit_with_no_readings_says_so(tmp_path):
    path = station(tmp_path)
    result = run(path, "water", "latest", "rw-9")
    assert result.exit_code != 0
    assert "no readings" in result.output


def test_the_listing_comes_out_as_csv(tmp_path):
    path = station(tmp_path)
    reading(path)
    result = run(path, "--quiet", "water", "list", "--format", "csv")
    assert result.output.splitlines()[0].startswith("taken at,unit,temperature")
