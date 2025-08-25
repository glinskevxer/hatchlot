"""A season on the command line, in the order somebody would actually type it.

Every one of these commands has its own tests. What this walks is the state that
carries between them: a lot ponded by one command is fed by another and shows up
in a report built by a third, off one database file that was opened and closed
eight times in between.
"""

from click.testing import CliRunner

from hatchlot.cli import main


def run(path, *args):
    return CliRunner().invoke(main, ["--database", path, *args])


def ok(path, *args):
    result = run(path, *args)
    assert result.exit_code == 0, result.output
    return result


def station(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    ok(path, "station", "init", "--code", "cold-creek", "--name", "Cold Creek")
    ok(
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
        "600",
    )
    for unit in ("rw-1", "rw-2"):
        ok(
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
            "450",
            "--source",
            "sp-1",
        )
    return path


def test_a_station_is_set_up_and_reads_back(tmp_path):
    path = station(tmp_path)
    assert "Cold Creek" in ok(path, "station", "show").output
    assert "2 units" in ok(path, "station", "units").output
    assert "600 gpm" in ok(path, "station", "water").output


def test_a_lot_is_ponded_fed_and_reported_on(tmp_path):
    path = station(tmp_path)
    ok(
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
    )
    for day, amount in (("2025-03-01", "22"), ("2025-03-02", "23")):
        ok(
            path,
            "feed",
            "record",
            "--lot",
            "2024-CHK-01",
            "--day",
            day,
            "--amount",
            amount,
            "--feed-lot",
            "FL-001",
        )
    totals = ok(path, "feed", "totals", "--from", "2025-03-01", "--to", "2025-03-31")
    assert "45" in totals.output
    report = ok(path, "report", "production", "--from", "2025-03-01", "--to", "2025-03-31")
    assert "2024-CHK-01" in report.output
    assert "Production report" in report.output


def test_mortality_moves_the_lot_the_ledger_and_the_report_together(tmp_path):
    path = station(tmp_path)
    ok(
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
    )
    ok(
        path,
        "lot",
        "mortality",
        "2024-CHK-01",
        "--day",
        "2025-03-05",
        "--count",
        "1000",
        "--reason",
        "gill damage after a screen failure",
    )
    show = ok(path, "lot", "show", "2024-CHK-01")
    assert "39000" in show.output
    assert "0 disagreements" in ok(path, "lot", "reconcile").output
    history = ok(path, "report", "lot", "2024-CHK-01")
    assert "mortality" in history.output


def test_readings_import_and_show_up_in_the_excursions(tmp_path):
    path = station(tmp_path)
    export = tmp_path / "logger.csv"
    export.write_text(
        "DateTime,Temp_F,Unit,DO_mgL\n"
        "2025-03-01 06:00,50,RW-1,9.1\n"
        "2025-03-01 18:00,51,RW-1,5.2\n"
        "2025-03-02 06:00,51,RW-1,5.0\n"
        "2025-03-02 18:00,52,RW-1,8.8\n",
        encoding="utf-8",
    )
    ok(path, "import", "readings", str(export))
    assert "4 readings" in ok(path, "water", "list").output
    excursions = ok(path, "water", "excursions")
    assert "low_oxygen" in excursions.output
    assert "1 excursion" in excursions.output


def test_the_same_export_arriving_twice_changes_nothing(tmp_path):
    path = station(tmp_path)
    export = tmp_path / "logger.csv"
    export.write_text(
        "DateTime,Temp_F,Unit,DO_mgL\n2025-03-01 06:00,50,RW-1,9.1\n", encoding="utf-8"
    )
    ok(path, "import", "readings", str(export))
    ok(path, "import", "readings", str(export))
    assert "1 reading" in ok(path, "water", "list").output


def test_a_lot_moves_between_units_and_the_inventory_follows(tmp_path):
    path = station(tmp_path)
    ok(
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
    )
    ok(path, "lot", "move", "2024-CHK-01", "--to", "rw-2")
    inventory = ok(path, "report", "inventory", "--as-of", "2025-03-31")
    assert "RW-2" in inventory.output
    assert "RW-1" not in inventory.output.split("\n")[2]


def test_the_inventory_exports_to_a_file_a_spreadsheet_can_read(tmp_path):
    path = station(tmp_path)
    ok(
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
    )
    out = tmp_path / "inventory.csv"
    ok(path, "report", "inventory", "--as-of", "2025-03-31", "--csv", str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("lot,unit,fish,biomass,biomass_unit")
    assert "2024-CHK-01" in lines[1]


def test_the_calculators_agree_with_what_the_database_says(tmp_path):
    path = station(tmp_path)
    ok(
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
    )
    off_the_lot = ok(path, "feed", "rate", "--lot", "2024-CHK-01", "--water", "10")
    by_hand = ok(path, "calc", "ration", "--biomass", "100", "--weight", "2.5", "--water", "10")
    assert "rate percent" in off_the_lot.output
    assert "rate percent" in by_hand.output
    rate_from_lot = off_the_lot.output.split("rate percent")[1].split("\n")[0].strip()
    rate_by_hand = by_hand.output.split("rate percent")[1].split("\n")[0].strip()
    assert rate_from_lot == rate_by_hand


def test_a_refusal_on_the_command_line_leaves_the_database_alone(tmp_path):
    path = station(tmp_path)
    ok(
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
        "100",
        "--weight",
        "2.5",
    )
    failed = run(
        path,
        "lot",
        "mortality",
        "2024-CHK-01",
        "--day",
        "2025-03-05",
        "--count",
        "500",
        "--reason",
        "an impossible number",
    )
    assert failed.exit_code == 2
    assert "100" in ok(path, "lot", "show", "2024-CHK-01").output
    assert "0 disagreements" in ok(path, "lot", "reconcile").output
