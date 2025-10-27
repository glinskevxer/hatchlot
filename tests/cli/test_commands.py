from click.testing import CliRunner

from hatchlot.cli import main
from hatchlot.cli.commands import missing_help, walk


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def test_the_listing_finds_every_group():
    entries = walk(main)
    groups = {entry.group for entry in entries}
    for name in ("station", "lot", "feed", "water", "report", "calc", "plan"):
        assert name in groups


def test_the_listing_finds_the_top_level_commands_too():
    paths = {entry.path for entry in walk(main)}
    assert "doctor" in paths
    assert "version" in paths


def test_every_command_says_what_it_does():
    assert missing_help(walk(main)) == ()


def test_the_command_paths_read_the_way_they_are_typed():
    paths = {entry.path for entry in walk(main)}
    assert "station add-unit" in paths
    assert "lot pond" in paths


def test_the_commands_command_prints_them():
    result = run("commands")
    assert result.exit_code == 0
    assert "station add-unit" in result.output
    assert "lot pond" in result.output


def test_the_listing_can_be_narrowed_to_one_group():
    result = CliRunner().invoke(main, ["commands", "--group", "lot"])
    assert "lot pond" in result.output
    assert "station add-unit" not in result.output
    assert "commands" in result.output


def test_a_group_that_does_not_exist_lists_nothing():
    result = CliRunner().invoke(main, ["commands", "--group", "nothing"])
    assert "0 commands" in result.output


def test_the_listing_comes_out_as_csv():
    result = run("commands", "--format", "csv")
    assert result.output.splitlines()[0] == "command,does"


def test_the_readme_shows_commands_that_exist():
    from pathlib import Path

    import hatchlot

    readme = (Path(hatchlot.__file__).parent.parent.parent / "README.md").read_text(
        encoding="utf-8"
    )
    paths = {entry.path for entry in walk(main)}
    for path in ("station init", "lot pond", "report production", "calc loading"):
        assert path in readme
        assert path in paths
