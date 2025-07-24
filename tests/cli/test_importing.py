from click.testing import CliRunner

from hatchlot.cli import main

GOOD = "DateTime,Temp_F,Unit,DO_mgL\n2025-03-01 06:00,50,RW-1,9.1\n2025-03-02 06:00,51.8,RW-1,9.0\n"


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def station(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    run(path, "station", "init", "--code", "cc", "--name", "Cold Creek")
    return path


def write(tmp_path, text=GOOD, name="export.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_logger_export_imports_and_shows_up_in_the_readings(tmp_path):
    path = station(tmp_path)
    result = run(path, "import", "readings", write(tmp_path))
    assert result.exit_code == 0
    assert "2 rows in" in result.output
    assert "2 readings" in run(path, "water", "list").output


def test_the_temperature_arrives_in_celsius(tmp_path):
    path = station(tmp_path)
    run(path, "import", "readings", write(tmp_path))
    assert "10 degC" in run(path, "water", "list").output


def test_importing_the_same_file_twice_does_nothing_the_second_time(tmp_path):
    path = station(tmp_path)
    source = write(tmp_path)
    run(path, "import", "readings", source)
    second = run(path, "import", "readings", source)
    assert "already held" in second.output or "already imported" in second.output
    assert "2 readings" in run(path, "water", "list").output


def test_a_dry_run_writes_nothing(tmp_path):
    path = station(tmp_path)
    result = run(path, "import", "readings", write(tmp_path), "--dry-run")
    assert result.exit_code == 0
    assert "0 readings" in run(path, "water", "list").output


def test_a_file_with_a_bad_row_imports_the_rest_and_says_so(tmp_path):
    text = GOOD + "2025-03-03 06:00,not a number,RW-1,9.0\n"
    path = station(tmp_path)
    result = run(path, "import", "readings", write(tmp_path, text))
    assert "1 rejected row" in result.output
    assert "2 readings" in run(path, "water", "list").output


def test_a_file_that_is_mostly_junk_is_refused(tmp_path):
    text = "DateTime,Temp_F,Unit\n" + "".join(
        f"2025-03-{day:02d} 06:00,bad,RW-1\n" for day in range(1, 6)
    )
    path = station(tmp_path)
    assert run(path, "import", "readings", write(tmp_path, text)).exit_code == 2


def test_a_file_that_is_not_there_is_a_usage_error(tmp_path):
    path = station(tmp_path)
    assert run(path, "import", "readings", str(tmp_path / "nothing.csv")).exit_code != 0


def test_a_check_reads_the_file_without_writing_anything(tmp_path):
    path = station(tmp_path)
    result = run(path, "import", "check", write(tmp_path))
    assert "2 rows would read" in result.output
    assert "0 readings" in run(path, "water", "list").output


def test_a_check_lists_the_rows_that_would_not_read(tmp_path):
    text = GOOD + "2025-03-03 06:00,bad,RW-1,9.0\n"
    path = station(tmp_path)
    result = run(path, "import", "check", write(tmp_path, text))
    assert "temperature" in result.output


def test_a_column_mapping_can_be_given_on_the_command_line(tmp_path):
    text = "when,unit,celsius\n2025-03-01 06:00,RW-2,11\n"
    path = station(tmp_path)
    result = run(
        path,
        "import",
        "readings",
        write(tmp_path, text, name="other.csv"),
        "--columns",
        "when=taken_at,unit=container,celsius=temperature",
    )
    assert result.exit_code == 0
    assert "RW-2" in run(path, "water", "list").output


def test_a_broken_column_mapping_is_refused(tmp_path):
    path = station(tmp_path)
    result = run(path, "import", "readings", write(tmp_path), "--columns", "no-equals-sign")
    assert result.exit_code == 2


def test_the_built_in_profile_can_be_printed(tmp_path):
    result = run(station(tmp_path), "import", "profile")
    assert "DateTime" in result.output
    assert "Temp_F" in result.output
