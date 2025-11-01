from click.testing import CliRunner

from hatchlot.cli import main


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def loud(*args):
    return CliRunner().invoke(main, list(args))


def test_a_sample_inside_its_limit_reads_clear():
    result = run("permit", "sample", "--intake", "2", "--outfall", "4", "--limit", "5")
    assert result.exit_code == 0
    assert "over" in result.output
    assert "no" in result.output


def test_the_net_and_the_gross_are_different_answers():
    net = run("permit", "sample", "--intake", "4", "--outfall", "8", "--limit", "5").output
    gross = run(
        "permit", "sample", "--intake", "4", "--outfall", "8", "--limit", "5", "--gross"
    ).output
    assert "yes" in gross
    assert "yes" not in net.split("over")[1]


def test_a_mass_limit_needs_a_flow():
    result = run(
        "permit",
        "sample",
        "--intake",
        "0",
        "--outfall",
        "6",
        "--limit",
        "5",
        "--basis",
        "mass_per_day",
    )
    assert result.exit_code == 2


def test_a_mass_limit_with_a_flow_answers():
    result = run(
        "permit",
        "sample",
        "--intake",
        "0",
        "--outfall",
        "6",
        "--limit",
        "5",
        "--basis",
        "mass_per_day",
        "--flow",
        "1000",
    )
    assert result.exit_code == 0
    assert "value against the limit" in result.output


def test_a_feed_based_limit_needs_the_feed_as_well():
    result = run(
        "permit",
        "sample",
        "--intake",
        "0",
        "--outfall",
        "6",
        "--limit",
        "1",
        "--basis",
        "feed_based",
        "--flow",
        "1000",
    )
    assert result.exit_code == 2


def test_a_negative_reading_is_refused():
    result = run("permit", "sample", "--intake", "-1", "--outfall", "4", "--limit", "5")
    assert result.exit_code == 2


def test_a_settling_pond_that_works_shows_as_a_removal():
    result = run("permit", "removal", "--intake", "10", "--outfall", "4")
    assert "removal  0.60" in result.output
    assert "adding" in result.output


def test_a_station_that_adds_solids_says_so():
    result = run("permit", "removal", "--intake", "4", "--outfall", "10")
    assert "yes" in result.output


def test_a_removal_against_nothing_coming_in_is_refused():
    assert run("permit", "removal", "--intake", "0", "--outfall", "4").exit_code == 2


def test_the_feed_ceiling_turns_a_permit_into_a_production_plan():
    result = run("permit", "feed-ceiling", "--limit", "5", "--flow", "1000")
    assert result.exit_code == 0
    assert "feed allowed" in result.output
    assert "solids" in result.output


def test_a_feed_ceiling_over_no_days_is_refused():
    assert (
        run("permit", "feed-ceiling", "--limit", "5", "--flow", "1000", "--days", "0").exit_code
        == 2
    )


def test_the_loading_off_a_month_of_feeding():
    result = loud("permit", "loading", "--feed", "1000")
    assert "solids" in result.output
    assert "250" in result.output
    assert "off 1000 kg of feed" in result.output


def test_a_negative_feed_is_refused():
    assert run("permit", "loading", "--feed", "-1").exit_code == 2


def test_the_permit_group_lists_its_commands():
    result = run("permit", "--help")
    assert "sample" in result.output
    assert "feed-ceiling" in result.output
