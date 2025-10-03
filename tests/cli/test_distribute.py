from click.testing import CliRunner

from hatchlot.cli import main

WINDOW = ["--from", "2025-04-01", "--to", "2025-05-31"]


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def loud(*args):
    return CliRunner().invoke(main, list(args))


def test_the_requests_read_back_with_their_biomass():
    result = loud(
        "distribute",
        "requests",
        "--request",
        "SR-001:LAKE-A:CHK:10000:20",
        *WINDOW,
    )
    assert result.exit_code == 0
    assert "LAKE-A" in result.output
    assert "1 request" in result.output


def test_a_request_of_the_wrong_shape_is_refused():
    result = run("distribute", "requests", "--request", "SR-001:LAKE-A", *WINDOW)
    assert result.exit_code == 2


def test_an_allocation_fills_the_top_of_the_list_first():
    result = loud(
        "distribute",
        "allocate",
        "--request",
        "SR-001:LAKE-A:CHK:10000:20:1",
        "--request",
        "SR-002:LAKE-B:CHK:10000:20:9",
        "--offer",
        "2024-CHK-01:CHK:10000:20",
        *WINDOW,
    )
    assert result.exit_code == 0
    assert "SR-001" in result.output
    assert "unfilled: SR-002" in result.output


def test_a_pro_rata_allocation_gives_everybody_something():
    result = loud(
        "distribute",
        "allocate",
        "--request",
        "SR-001:LAKE-A:CHK:10000:20:1",
        "--request",
        "SR-002:LAKE-B:CHK:10000:20:9",
        "--offer",
        "2024-CHK-01:CHK:10000:20",
        "--policy",
        "pro_rata",
        *WINDOW,
    )
    assert "SR-001" in result.output
    assert "SR-002" in result.output
    assert "0 requests unfilled" in result.output


def test_an_offer_of_the_wrong_shape_is_refused():
    result = run(
        "distribute",
        "allocate",
        "--request",
        "SR-001:LAKE-A:CHK:10000:20",
        "--offer",
        "2024-CHK-01:CHK",
        *WINDOW,
    )
    assert result.exit_code == 2


def test_an_allocation_with_no_requests_is_refused():
    result = run("distribute", "allocate", "--offer", "2024-CHK-01:CHK:10000:20", *WINDOW)
    assert result.exit_code == 2


def test_a_haul_is_sized_and_counted():
    result = run(
        "distribute",
        "haul",
        "--fish",
        "100000",
        "--weight",
        "20",
        "--hours",
        "4",
        "--water",
        "10",
    )
    assert result.exit_code == 0
    assert "loads" in result.output
    assert "oxygen per load" in result.output


def test_a_haul_with_a_receiving_water_says_how_long_to_temper():
    result = run(
        "distribute",
        "haul",
        "--fish",
        "10000",
        "--weight",
        "20",
        "--hours",
        "4",
        "--water",
        "10",
        "--receiving",
        "14",
    )
    assert "tempering minutes" in result.output
    assert "40" in result.output


def test_a_haul_of_no_fish_is_refused():
    result = run(
        "distribute",
        "haul",
        "--fish",
        "0",
        "--weight",
        "20",
        "--hours",
        "4",
        "--water",
        "10",
    )
    assert result.exit_code == 2


def test_the_density_table_falls_as_the_water_warms():
    result = loud("distribute", "density", "--hours", "4")
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line and line[0].isdigit()]
    values = [line.split()[-1] for line in lines]
    assert values == sorted(values, reverse=True)


def test_a_density_over_no_hours_is_refused():
    assert run("distribute", "density", "--hours", "0").exit_code == 2


def test_the_distribute_group_lists_its_commands():
    result = run("distribute", "--help")
    assert "allocate" in result.output
    assert "haul" in result.output
