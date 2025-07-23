from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def station(tmp_path, fish="50000"):
    path = str(tmp_path / "station.sqlite3")
    run(path, "station", "init", "--code", "cc", "--name", "Cold Creek")
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
    run(
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
        fish,
        "--weight",
        "2.5",
    )
    run(
        path,
        "feed",
        "record",
        "--lot",
        "2024-CHK-01",
        "--day",
        "2025-03-01",
        "--amount",
        "25",
        "--feed-lot",
        "FL-001",
    )
    run(
        path,
        "lot",
        "mortality",
        "2024-CHK-01",
        "--day",
        "2025-03-05",
        "--count",
        "500",
        "--reason",
        "fungus",
    )
    return path


def test_the_production_report_prints(tmp_path):
    path = station(tmp_path)
    result = run(path, "report", "production", "--from", "2025-03-01", "--to", "2025-03-31")
    assert result.exit_code == 0
    assert "Production report" in result.output
    assert "Cold Creek" in result.output
    assert "2024-CHK-01" in result.output


def test_the_production_report_needs_a_station(tmp_path):
    path = str(tmp_path / "empty.sqlite3")
    result = run(path, "report", "production", "--from", "2025-03-01", "--to", "2025-03-31")
    assert result.exit_code == 2
    assert "not found" in result.output


def test_a_backwards_window_is_refused(tmp_path):
    path = station(tmp_path)
    result = run(path, "report", "production", "--from", "2025-03-31", "--to", "2025-03-01")
    assert result.exit_code == 2


def test_the_lot_report_shows_the_timeline(tmp_path):
    path = station(tmp_path)
    result = run(path, "report", "lot", "2024-CHK-01")
    assert result.exit_code == 0
    assert "Lot history" in result.output
    assert "mortality" in result.output
    assert "feeding" in result.output


def test_the_lot_report_can_be_narrowed_and_limited(tmp_path):
    path = station(tmp_path)
    narrow = run(path, "report", "lot", "2024-CHK-01", "--from", "2025-03-01", "--to", "2025-03-31")
    assert "2025-01-15" not in narrow.output
    limited = run(path, "report", "lot", "2024-CHK-01", "--limit", "1")
    assert "more events not shown" in limited.output


def test_a_limit_of_nothing_is_refused(tmp_path):
    path = station(tmp_path)
    assert run(path, "report", "lot", "2024-CHK-01", "--limit", "0").exit_code == 2


def test_the_inventory_prints(tmp_path):
    path = station(tmp_path)
    result = run(path, "report", "inventory", "--as-of", "2025-03-31")
    assert result.exit_code == 0
    assert "2024-CHK-01" in result.output
    assert "lots checked" not in result.output


def test_the_inventory_can_be_written_to_a_file(tmp_path):
    path = station(tmp_path)
    out = tmp_path / "inventory.csv"
    result = run(path, "report", "inventory", "--as-of", "2025-03-31", "--csv", str(out))
    assert result.exit_code == 0
    assert "1 rows written" in result.output
    assert out.read_text(encoding="utf-8").splitlines()[0].startswith("lot,unit,fish")


def test_writing_the_inventory_somewhere_impossible_is_refused(tmp_path):
    path = station(tmp_path)
    result = run(
        path,
        "report",
        "inventory",
        "--as-of",
        "2025-03-31",
        "--csv",
        str(tmp_path / "nowhere" / "inventory.csv"),
    )
    assert result.exit_code == 2


def test_the_report_group_lists_its_commands(tmp_path):
    result = run(str(tmp_path / "x.sqlite3"), "report", "--help")
    assert "production" in result.output
    assert "inventory" in result.output
