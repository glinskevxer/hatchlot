from click.testing import CliRunner

from hatchlot.cli import main


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def loud(*args):
    return CliRunner().invoke(main, list(args))


def test_an_order_says_how_many_tags_to_buy():
    result = run(
        "mark",
        "order",
        "--lot",
        "2024-CHK-01",
        "--fish",
        "100000",
        "--type",
        "adipose_clip",
        "--type",
        "coded_wire_tag",
        "--tag",
        "05-12-34",
    )
    assert result.exit_code == 0
    assert "tags to order" in result.output
    assert "105264" in result.output


def test_a_tag_plan_with_no_tag_code_is_refused():
    result = run(
        "mark",
        "order",
        "--lot",
        "2024-CHK-01",
        "--fish",
        "1000",
        "--type",
        "coded_wire_tag",
    )
    assert result.exit_code == 2


def test_a_malformed_tag_code_is_refused():
    result = run(
        "mark",
        "order",
        "--lot",
        "2024-CHK-01",
        "--fish",
        "1000",
        "--type",
        "coded_wire_tag",
        "--tag",
        "nonsense",
    )
    assert result.exit_code == 2


def test_a_partial_marking_plan_orders_fewer_tags():
    whole = run("mark", "order", "--lot", "L", "--fish", "100000").output
    quarter = run("mark", "order", "--lot", "L", "--fish", "100000", "--rate", "0.25").output
    assert "25000" in quarter
    assert whole != quarter


def test_a_run_that_hit_its_rate_is_accepted():
    result = run(
        "mark",
        "check",
        "--lot",
        "2024-CHK-01",
        "--presented",
        "10000",
        "--marked",
        "9900",
        "--sampled",
        "200",
        "--found",
        "199",
    )
    assert result.exit_code == 0
    assert "accepted" in result.output


def test_a_run_that_missed_its_rate_is_rejected():
    result = run(
        "mark",
        "check",
        "--lot",
        "2024-CHK-01",
        "--presented",
        "10000",
        "--marked",
        "8000",
        "--sampled",
        "200",
        "--found",
        "160",
    )
    assert "rejected" in result.output
    assert "shortfall" in result.output


def test_a_check_that_found_more_than_it_sampled_is_refused():
    result = run(
        "mark",
        "check",
        "--lot",
        "2024-CHK-01",
        "--presented",
        "10000",
        "--marked",
        "9900",
        "--sampled",
        "200",
        "--found",
        "500",
    )
    assert result.exit_code == 2


def test_a_group_adds_its_runs_up_and_reports_retention():
    result = loud(
        "mark",
        "group",
        "--lot",
        "2024-CHK-01",
        "--run",
        "10000:9900:200:199:195:14",
        "--run",
        "5000:4900:200:198:190:14",
    )
    assert result.exit_code == 0
    assert "retention" in result.output
    assert "15000" in result.output


def test_a_group_run_of_the_wrong_shape_is_refused():
    result = run("mark", "group", "--lot", "L", "--run", "10000:9900")
    assert result.exit_code != 0


def test_a_group_with_no_runs_is_refused():
    assert run("mark", "group", "--lot", "L").exit_code == 2


def test_the_rate_command_works_one_out():
    result = CliRunner().invoke(
        main,
        ["--quiet", "--places", "4", "mark", "rate", "--marked", "9000", "--population", "10000"],
    )
    assert "0.9000" in result.output


def test_a_rate_over_the_population_is_refused():
    assert run("mark", "rate", "--marked", "11000", "--population", "10000").exit_code == 2


def test_the_mark_group_lists_its_commands():
    result = run("mark", "--help")
    assert "order" in result.output
    assert "check" in result.output
