from click.testing import CliRunner

from hatchlot.cli import main


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def test_the_loading_calculator_says_which_limit_binds():
    result = run(
        "calc",
        "loading",
        "--species",
        "chinook",
        "--flow",
        "500",
        "--volume",
        "3178",
        "--weight",
        "2.5",
    )
    assert result.exit_code == 0
    assert "binding" in result.output
    assert "allowed" in result.output


def test_a_short_flow_makes_the_flow_index_bind():
    result = run(
        "calc",
        "loading",
        "--species",
        "chk",
        "--flow",
        "60",
        "--volume",
        "5000",
        "--weight",
        "2.5",
    )
    assert "flow_index" in result.output


def test_a_species_the_station_does_not_run_is_refused():
    result = run(
        "calc",
        "loading",
        "--species",
        "walleye",
        "--flow",
        "500",
        "--volume",
        "3178",
        "--weight",
        "2.5",
    )
    assert result.exit_code == 2


def test_the_ration_calculator_splits_the_day():
    result = run("calc", "ration", "--biomass", "1000", "--weight", "1", "--water", "10")
    assert result.exit_code == 0
    assert "rate percent" in result.output
    assert "per feeding" in result.output


def test_a_ration_for_a_weightless_fish_is_refused():
    result = run("calc", "ration", "--biomass", "1000", "--weight", "0", "--water", "10")
    assert result.exit_code == 2


def test_the_oxygen_calculator_answers_with_and_without_a_reading():
    plain = run("calc", "oxygen", "--water", "10")
    assert "saturation" in plain.output
    assert "measured" not in plain.output
    with_reading = run("calc", "oxygen", "--water", "10", "--measured", "9")
    assert "percent of saturation" in with_reading.output


def test_altitude_takes_oxygen_out_of_the_water():
    low = run("calc", "oxygen", "--water", "10").output
    high = run("calc", "oxygen", "--water", "10", "--elevation", "1500").output
    assert low != high


def test_a_water_outside_the_solubility_table_is_refused():
    assert run("calc", "oxygen", "--water", "40").exit_code == 2


def test_the_degree_day_calculator_answers_for_every_mark():
    result = run("calc", "degree-days", "--species", "chinook", "--water", "10")
    assert result.exit_code == 0
    assert "eye_up days" in result.output
    assert "hatch days" in result.output
    assert "swim_up days" in result.output


def test_a_water_at_the_zero_point_never_gets_there():
    result = run("calc", "degree-days", "--species", "chinook", "--water", "0")
    assert result.exit_code != 0


def test_the_species_command_prints_the_constants():
    result = run("calc", "species", "coho")
    assert result.exit_code == 0
    assert "coho salmon" in result.output
    assert "hatch units" in result.output


def test_a_calculator_comes_out_as_csv_when_asked():
    result = run("calc", "species", "chk", "--format", "csv")
    assert result.output.splitlines()[0].startswith("code,name")


def test_the_calc_group_lists_its_commands():
    result = run("calc", "--help")
    assert "loading" in result.output
    assert "degree-days" in result.output
