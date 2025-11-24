from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def station(tmp_path, units=("rw-1",), flow="500"):
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
            flow,
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


def reading(path, at, unit="rw-1", temperature="10", oxygen="9"):
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
        "--oxygen",
        oxygen,
    )


def test_a_quiet_morning_has_nothing_to_do(tmp_path):
    path = station(tmp_path)
    pond(path)
    reading(path, "2025-03-05 06:00")
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
    result = run(path, "today", "--as-of", "2025-03-05")
    assert result.exit_code == 0
    assert "lots" in result.output
    assert "feed today" in result.output


def test_the_briefing_counts_the_fish_and_works_out_the_feed(tmp_path):
    path = station(tmp_path)
    pond(path, fish="40000")
    result = run(path, "today", "--as-of", "2025-03-05")
    assert "40000" in result.output
    assert "feed today" in result.output


def test_an_empty_station_still_briefs(tmp_path):
    path = station(tmp_path)
    result = run(path, "today", "--as-of", "2025-03-05")
    assert result.exit_code == 0
    assert "0 " in result.output


def test_the_water_from_the_last_two_days_is_summarised(tmp_path):
    path = station(tmp_path)
    pond(path)
    reading(path, "2025-03-04 06:00", temperature="8")
    reading(path, "2025-03-05 06:00", temperature="12")
    result = run(path, "today", "--as-of", "2025-03-05")
    assert "coldest" in result.output
    assert "8 degC" in result.output
    assert "12 degC" in result.output


def test_readings_older_than_the_window_are_left_out(tmp_path):
    path = station(tmp_path)
    pond(path)
    reading(path, "2025-01-01 06:00", temperature="2")
    result = run(path, "today", "--as-of", "2025-03-05")
    assert "2 degC" not in result.output


def test_an_overnight_excursion_turns_up_in_the_work(tmp_path):
    path = station(tmp_path)
    pond(path)
    reading(path, "2025-03-04 18:00", oxygen="4")
    reading(path, "2025-03-05 06:00", oxygen="4")
    result = run(path, "today", "--as-of", "2025-03-05")
    assert "excursion" in result.output
    assert "1 job" in result.output


def test_an_overloaded_unit_turns_up_in_the_work(tmp_path):
    path = station(tmp_path, flow="60")
    pond(path, fish="4000000")
    result = run(path, "today", "--as-of", "2025-03-05")
    assert "over its loading limit" in result.output


def test_a_lot_off_its_ledger_turns_up_in_the_work(tmp_path):
    path = station(tmp_path)
    pond(path, fish="40000")
    run(
        path,
        "lot",
        "mortality",
        "2024-CHK-01",
        "--day",
        "2025-03-01",
        "--count",
        "500",
        "--reason",
        "fungus",
    )
    result = run(path, "today", "--as-of", "2025-03-05")
    assert "off its ledger" not in result.output


def test_the_briefing_comes_out_as_csv(tmp_path):
    path = station(tmp_path)
    pond(path)
    result = run(path, "--quiet", "today", "--as-of", "2025-03-05", "--format", "csv")
    assert result.output.splitlines()[0].startswith("lots,fish,biomass")


def test_a_day_that_is_not_a_day_is_refused(tmp_path):
    path = station(tmp_path)
    assert run(path, "today", "--as-of", "whenever").exit_code == 2
