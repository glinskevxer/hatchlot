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


def pond(path, code="2024-CHK-01", unit="rw-1", fish="50000", weight="2.5"):
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
        weight,
    )


def test_ponding_a_lot_writes_both_the_lot_and_the_ledger(tmp_path):
    path = station(tmp_path)
    assert pond(path).exit_code == 0
    show = run(path, "lot", "show", "2024-CHK-01")
    assert "50000" in show.output
    assert "difference" in show.output


def test_a_lot_in_a_unit_that_is_not_there_is_refused(tmp_path):
    path = station(tmp_path)
    assert pond(path, unit="rw-9").exit_code == 2


def test_a_lot_code_that_is_not_a_lot_code_is_refused(tmp_path):
    path = station(tmp_path)
    assert pond(path, code="not-a-lot").exit_code == 2


def test_the_lots_list_and_count(tmp_path):
    path = station(tmp_path)
    pond(path, code="2024-CHK-01")
    pond(path, code="2024-CHK-02")
    listing = run(path, "lot", "list")
    assert "2024-CHK-01" in listing.output
    assert "2 lots" in listing.output


def test_a_sample_moves_the_mean_weight(tmp_path):
    path = station(tmp_path)
    pond(path, weight="2.5")
    result = run(path, "lot", "sample", "2024-CHK-01", "--weight", "4")
    assert result.exit_code == 0
    assert "4 g" in result.output


def test_a_sample_of_no_weight_is_refused(tmp_path):
    path = station(tmp_path)
    pond(path)
    assert run(path, "lot", "sample", "2024-CHK-01", "--weight", "0").exit_code == 2


def test_a_mortality_comes_off_the_lot_and_goes_on_the_ledger(tmp_path):
    path = station(tmp_path)
    pond(path, fish="50000")
    result = run(
        path,
        "lot",
        "mortality",
        "2024-CHK-01",
        "--day",
        "2025-02-01",
        "--count",
        "500",
        "--reason",
        "fungus",
    )
    assert result.exit_code == 0
    assert "49500" in result.output
    assert "0 disagreements" in run(path, "lot", "reconcile").output


def test_a_mortality_bigger_than_the_lot_is_refused(tmp_path):
    path = station(tmp_path)
    pond(path, fish="100")
    result = run(
        path,
        "lot",
        "mortality",
        "2024-CHK-01",
        "--day",
        "2025-02-01",
        "--count",
        "500",
        "--reason",
        "fungus",
    )
    assert result.exit_code == 2


def test_moving_a_lot_between_units(tmp_path):
    path = station(tmp_path, units=("rw-1", "rw-2"))
    pond(path)
    result = run(path, "lot", "move", "2024-CHK-01", "--to", "rw-2")
    assert result.exit_code == 0
    assert "RW-2" in result.output


def test_moving_a_lot_into_a_unit_that_is_not_there_is_refused(tmp_path):
    path = station(tmp_path)
    pond(path)
    assert run(path, "lot", "move", "2024-CHK-01", "--to", "rw-9").exit_code == 2


def test_showing_a_lot_that_is_not_there(tmp_path):
    path = station(tmp_path)
    result = run(path, "lot", "show", "2024-CHK-09")
    assert result.exit_code == 2
    assert "not found" in result.output


def test_the_reconcile_command_finds_a_lot_that_was_edited_behind_the_ledger(tmp_path):
    path = station(tmp_path)
    pond(path, fish="50000")
    run(path, "lot", "sample", "2024-CHK-01", "--weight", "3")
    assert "0 disagreements" in run(path, "lot", "reconcile").output


def test_the_lot_listing_comes_out_as_csv(tmp_path):
    path = station(tmp_path)
    pond(path)
    result = run(path, "--quiet", "lot", "list", "--format", "csv")
    assert result.output.splitlines()[0].startswith("lot,unit,fish")
