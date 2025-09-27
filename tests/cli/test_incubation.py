from click.testing import CliRunner

from hatchlot.cli import main


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def test_the_schedule_lands_every_mark_on_a_date():
    result = run(
        "incubate", "schedule", "--species", "chinook", "--spawned", "2024-09-13", "--water", "10"
    )
    assert result.exit_code == 0
    assert "eye_up" in result.output
    assert "hatch" in result.output
    assert "swim_up" in result.output


def test_a_colder_water_pushes_the_marks_out():
    warm = run(
        "incubate", "schedule", "--species", "chk", "--spawned", "2024-09-13", "--water", "12"
    ).output
    cold = run(
        "incubate", "schedule", "--species", "chk", "--spawned", "2024-09-13", "--water", "6"
    ).output
    assert warm != cold


def test_a_water_at_the_zero_point_is_refused():
    result = run(
        "incubate", "schedule", "--species", "chk", "--spawned", "2024-09-13", "--water", "0"
    )
    assert result.exit_code != 0


def test_a_species_the_station_does_not_run_is_refused():
    result = run(
        "incubate", "schedule", "--species", "walleye", "--spawned", "2024-09-13", "--water", "10"
    )
    assert result.exit_code == 2


def test_where_a_lot_is_and_whether_it_can_be_handled():
    green = run("incubate", "where", "--species", "chk", "--units", "10")
    assert "green" in green.output
    assert "no" in green.output
    tender = run("incubate", "where", "--species", "chk", "--units", "200")
    assert "yes" in tender.output
    eyed = run("incubate", "where", "--species", "chk", "--units", "500")
    assert "eye_up" in eyed.output


def test_a_shock_is_read_back_with_its_two_rates():
    result = run("incubate", "shock", "--green", "30000", "--eyed", "26000")
    assert result.exit_code == 0
    assert "eye up rate" in result.output
    assert "fertility" in result.output
    assert "believable" in result.output


def test_a_shock_against_a_standing_count_gives_two_different_rates():
    result = run("incubate", "shock", "--green", "30000", "--standing", "28000", "--eyed", "26000")
    lines = {
        line.split("  ")[0]: line.split("  ")[-1].strip() for line in result.output.splitlines()
    }
    assert lines["eye up rate"] != lines["fertility"]


def test_a_shock_that_found_more_eggs_than_were_there_is_refused():
    result = run("incubate", "shock", "--green", "1000", "--eyed", "2000")
    assert result.exit_code != 0


def test_a_poor_shock_is_not_believable():
    result = run("incubate", "shock", "--green", "30000", "--eyed", "3000")
    assert "believable" in result.output
    assert "no" in result.output


def test_the_capacity_command_counts_the_trays():
    result = run("incubate", "capacity", "--eggs", "30000")
    assert result.exit_code == 0
    assert "trays" in result.output
    assert "3" in result.output


def test_a_take_of_nothing_has_no_capacity_to_work_out():
    assert run("incubate", "capacity", "--eggs", "0").exit_code != 0


def test_the_stages_are_listed_in_order():
    result = run("incubate", "stages")
    lines = result.output.splitlines()
    assert "green" in lines[2]
    assert "written_off" in result.output


def test_the_incubate_group_lists_its_commands():
    result = run("incubate", "--help")
    assert "schedule" in result.output
    assert "shock" in result.output
