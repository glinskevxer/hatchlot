from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def station(tmp_path):
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
        "50000",
        "--weight",
        "2.5",
    )
    return path


def fed(path, day="2025-03-01", amount="10", lot="2024-CHK-01", feed_lot="FL-001"):
    return run(
        path,
        "feed",
        "record",
        "--lot",
        lot,
        "--day",
        day,
        "--amount",
        amount,
        "--feed-lot",
        feed_lot,
    )


def test_a_feeding_goes_on_and_comes_back(tmp_path):
    path = station(tmp_path)
    assert fed(path).exit_code == 0
    listing = run(path, "feed", "list")
    assert "FL-001" in listing.output
    assert "1 feeding" in listing.output


def test_feeding_a_lot_that_is_not_there_is_refused(tmp_path):
    path = station(tmp_path)
    assert fed(path, lot="2024-CHK-09").exit_code == 2


def test_a_feeding_of_nothing_is_refused(tmp_path):
    path = station(tmp_path)
    assert fed(path, amount="0").exit_code == 2


def test_the_feedings_narrow_to_a_lot_and_a_window(tmp_path):
    path = station(tmp_path)
    fed(path, day="2025-03-01")
    fed(path, day="2025-04-01")
    assert "2 feedings" in run(path, "feed", "list", "--lot", "2024-CHK-01").output
    assert (
        "1 feeding"
        in run(path, "feed", "list", "--from", "2025-03-01", "--to", "2025-03-31").output
    )


def test_the_totals_add_a_window_up_by_lot(tmp_path):
    path = station(tmp_path)
    fed(path, day="2025-03-01", amount="10")
    fed(path, day="2025-03-02", amount="15", feed_lot="FL-002")
    result = run(path, "feed", "totals", "--from", "2025-03-01", "--to", "2025-03-31")
    assert "25" in result.output
    assert "FL-001, FL-002" in result.output


def test_the_conversion_reports_both_ratios(tmp_path):
    path = station(tmp_path)
    fed(path, day="2025-03-01", amount="100")
    result = run(
        path,
        "feed",
        "conversion",
        "--lot",
        "2024-CHK-01",
        "--from",
        "2025-03-01",
        "--to",
        "2025-03-31",
        "--opening",
        "50",
    )
    assert result.exit_code == 0
    assert "economic" in result.output
    assert "biological" in result.output


def test_a_conversion_over_a_period_with_no_gain_is_refused(tmp_path):
    path = station(tmp_path)
    fed(path, day="2025-03-01", amount="100")
    result = run(
        path,
        "feed",
        "conversion",
        "--lot",
        "2024-CHK-01",
        "--from",
        "2025-03-01",
        "--to",
        "2025-03-31",
        "--opening",
        "500",
    )
    assert result.exit_code == 2


def test_the_rate_command_answers_off_the_lot_itself(tmp_path):
    path = station(tmp_path)
    result = run(path, "feed", "rate", "--lot", "2024-CHK-01", "--water", "10")
    assert result.exit_code == 0
    assert "rate percent" in result.output
    assert "owed" in result.output


def test_the_rate_for_a_lot_that_is_not_there_is_refused(tmp_path):
    path = station(tmp_path)
    assert run(path, "feed", "rate", "--lot", "2024-CHK-09", "--water", "10").exit_code == 2


def test_the_feeding_list_comes_out_as_csv(tmp_path):
    path = station(tmp_path)
    fed(path)
    result = run(path, "--quiet", "feed", "list", "--format", "csv")
    assert result.output.splitlines()[0].startswith("day,lot,feed lot")
