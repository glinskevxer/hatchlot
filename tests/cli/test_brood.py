from click.testing import CliRunner

from hatchlot.cli import main


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def loud(*args):
    return CliRunner().invoke(main, list(args))


def test_a_season_target_turns_into_a_number_of_hens():
    result = run("brood", "target", "--eggs", "100000")
    assert result.exit_code == 0
    assert "hens needed" in result.output
    assert "eggs per hen" in result.output


def test_bigger_hens_mean_fewer_of_them():
    small = run("brood", "target", "--eggs", "100000", "--length", "60").output
    big = run("brood", "target", "--eggs", "100000", "--length", "90").output
    assert small != big


def test_a_target_of_nothing_is_refused():
    assert run("brood", "target", "--eggs", "0").exit_code == 2


def test_a_fitted_model_can_be_passed_in():
    result = run(
        "brood",
        "target",
        "--eggs",
        "100000",
        "--scale",
        "0.01",
        "--exponent",
        "3.0",
    )
    assert result.exit_code == 0


def test_an_impossible_fitted_model_is_refused():
    result = run("brood", "target", "--eggs", "100000", "--scale", "0", "--exponent", "3.0")
    assert result.exit_code == 2


def test_a_von_bayer_count_reads_off_the_trough():
    result = run("brood", "count", "--trough", "30", "--volume", "10")
    assert result.exit_code == 0
    assert "egg diameter" in result.output
    assert "von bayer count" in result.output


def test_a_hand_count_wins_over_the_estimate():
    result = run("brood", "count", "--trough", "30", "--volume", "10", "--enumerated", "15000")
    assert "enumerated" in result.output
    assert "15000" in result.output


def test_a_hand_count_that_disagrees_wildly_still_wins():
    result = run("brood", "count", "--trough", "30", "--volume", "10", "--enumerated", "1")
    assert result.exit_code == 0
    assert "enumerated" in result.output


def test_a_trough_count_of_nothing_is_refused():
    assert run("brood", "count", "--trough", "0", "--volume", "10").exit_code == 2


def test_a_factorial_cross_lists_its_families():
    result = loud(
        "brood",
        "cross",
        "--dam",
        "F-1",
        "--dam",
        "F-2",
        "--sire",
        "M-1",
        "--sire",
        "M-2",
    )
    assert result.exit_code == 0
    assert "F-1xM-1" in result.output
    assert "4 families" in result.output


def test_a_cross_that_leans_on_one_buck_is_refused():
    result = run("brood", "cross", "--dam", "F-1", "--dam", "F-2", "--dam", "F-3", "--sire", "M-1")
    assert result.exit_code == 2
    assert "cross.sire_share" in result.output


def test_the_share_limit_can_be_relaxed_deliberately():
    result = run(
        "brood",
        "cross",
        "--dam",
        "F-1",
        "--dam",
        "F-2",
        "--sire",
        "M-1",
        "--max-share",
        "1",
    )
    assert result.exit_code == 0


def test_a_pairwise_cross_needs_the_sides_to_match():
    result = run(
        "brood",
        "cross",
        "--dam",
        "F-1",
        "--dam",
        "F-2",
        "--sire",
        "M-1",
        "--design",
        "pairwise",
    )
    assert result.exit_code == 2


def test_the_census_shows_what_a_lopsided_ratio_costs():
    even = run("brood", "census", "--males", "10", "--females", "10")
    lopsided = run("brood", "census", "--males", "1", "--females", "10")
    assert "20.00" in even.output
    assert "3.64" in lopsided.output


def test_a_run_missing_a_sex_has_no_effective_size():
    assert run("brood", "census", "--males", "0", "--females", "10").exit_code == 2


def test_the_brood_group_lists_its_commands():
    result = run("brood", "--help")
    assert "target" in result.output
    assert "cross" in result.output
