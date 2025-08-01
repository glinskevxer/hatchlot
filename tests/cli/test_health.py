from click.testing import CliRunner

from hatchlot.cli import main


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def treatment(*extra):
    return run(
        "health",
        "treatment",
        "--chemical",
        "formalin",
        "--concentration",
        "167",
        "--minutes",
        "60",
        "--water",
        "10",
        "--flow",
        "500",
        *extra,
    )


def test_a_flush_treatment_works_out_its_dose():
    result = treatment()
    assert result.exit_code == 0
    assert "dose" in result.output
    assert "exposure" in result.output


def test_a_static_bath_needs_a_volume_not_a_flow():
    result = run(
        "health",
        "treatment",
        "--chemical",
        "formalin",
        "--method",
        "static",
        "--concentration",
        "167",
        "--minutes",
        "60",
        "--water",
        "10",
        "--volume",
        "90",
    )
    assert result.exit_code == 0
    assert "static" in result.output


def test_a_flowing_treatment_with_no_flow_is_refused():
    result = run(
        "health",
        "treatment",
        "--chemical",
        "formalin",
        "--concentration",
        "167",
        "--minutes",
        "60",
        "--water",
        "10",
    )
    assert result.exit_code == 2


def test_a_concentration_over_the_ceiling_is_refused():
    result = run(
        "health",
        "treatment",
        "--chemical",
        "formalin",
        "--concentration",
        "400",
        "--minutes",
        "60",
        "--water",
        "10",
        "--flow",
        "500",
    )
    assert result.exit_code == 2
    assert "treatment.concentration" in result.output


def test_the_same_concentration_can_fail_on_warmer_water():
    warm = run(
        "health",
        "treatment",
        "--chemical",
        "formalin",
        "--concentration",
        "240",
        "--minutes",
        "60",
        "--water",
        "18",
        "--flow",
        "500",
    )
    assert warm.exit_code == 2


def test_a_treatment_that_would_pull_the_oxygen_under_is_refused():
    result = treatment("--inflow", "7", "--floor", "6")
    assert result.exit_code == 2
    assert "treatment.oxygen" in result.output


def test_a_treatment_with_room_in_the_oxygen_passes():
    assert treatment("--inflow", "11", "--floor", "6").exit_code == 0


def test_the_ceilings_are_listed_for_a_water():
    result = run("health", "ceiling", "--water", "10")
    assert "formalin" in result.output
    assert "hydrogen_peroxide" in result.output


def test_the_ceilings_fall_as_the_water_warms():
    cold = run("health", "ceiling", "--water", "8").output
    warm = run("health", "ceiling", "--water", "18").output
    assert cold != warm


def test_a_prescription_turns_into_an_inclusion_rate_and_a_feed_order():
    result = run(
        "health",
        "prescription",
        "--lot",
        "2024-CHK-01",
        "--drug",
        "oxytetracycline",
        "--start",
        "2025-03-01",
        "--biomass",
        "1000",
        "--feeding-rate",
        "2",
    )
    assert result.exit_code == 0
    assert "inclusion mg per kg feed" in result.output
    assert "withdrawal degree days" in result.output


def test_a_prescription_off_the_label_says_so():
    result = run(
        "health",
        "prescription",
        "--lot",
        "2024-CHK-01",
        "--drug",
        "florfenicol",
        "--dose",
        "15",
        "--days",
        "14",
        "--start",
        "2025-03-01",
        "--biomass",
        "1000",
        "--feeding-rate",
        "2",
    )
    assert "off label" in result.output
    assert "yes" in result.output


def test_a_prescription_at_an_impossible_feeding_rate_is_refused():
    result = run(
        "health",
        "prescription",
        "--lot",
        "2024-CHK-01",
        "--drug",
        "florfenicol",
        "--start",
        "2025-03-01",
        "--biomass",
        "1000",
        "--feeding-rate",
        "0",
    )
    assert result.exit_code == 2


def test_the_health_group_lists_its_commands():
    result = run("health", "--help")
    assert "treatment" in result.output
    assert "prescription" in result.output
