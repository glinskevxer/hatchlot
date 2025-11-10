import click
import pytest
from click.testing import CliRunner

from hatchlot import __version__
from hatchlot.cli.main import (
    EXIT_OK,
    EXIT_REFUSED,
    Context,
    describe_error,
    guard,
    main,
    run_guarded,
)
from hatchlot.errors import HatchlotError, NotFoundError, PolicyError, ValidationError


def run(*args):
    return CliRunner().invoke(main, list(args))


def test_the_help_comes_up():
    result = run("--help")
    assert result.exit_code == 0
    assert "coldwater salmonid hatchery" in result.output


def test_the_version_prints_the_package_version():
    result = run("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_the_version_command_says_which_database_it_would_use():
    result = run("--database", "/tmp/station.sqlite3", "version")
    assert result.exit_code == 0
    assert "/tmp/station.sqlite3" in result.output


def test_quiet_says_nothing():
    assert run("--quiet", "version").output == ""


def test_an_impossible_places_setting_is_refused():
    result = run("--places", "9", "version")
    assert result.exit_code != 0
    assert "places" in result.output


def test_the_context_carries_the_defaults():
    context = Context()
    assert context.database == ":memory:"
    assert context.places == 2
    assert not context.quiet


def test_each_kind_of_error_prints_its_own_first_word():
    assert describe_error(PolicyError("no", rule="loading.density")).startswith("refused by")
    assert describe_error(NotFoundError("lot", "L-1")).startswith("not found")
    assert describe_error(ValidationError("bad")).startswith("invalid")
    assert describe_error(HatchlotError("something")).startswith("error")


def test_a_guarded_run_of_something_fine_is_a_zero():
    assert run_guarded(lambda: None) == EXIT_OK


def test_a_guarded_run_of_a_refusal_is_a_two():
    def refuse() -> None:
        raise PolicyError("no", rule="x")

    assert run_guarded(refuse) == EXIT_REFUSED


def test_a_guarded_run_lets_an_unexpected_error_through():
    def broken() -> None:
        raise RuntimeError("that was not meant to happen")

    with pytest.raises(RuntimeError):
        run_guarded(broken)


def test_guard_exits_on_a_refusal_and_returns_on_success():
    guard(lambda: None)

    def refuse() -> None:
        raise ValidationError("bad")

    with pytest.raises(SystemExit) as excinfo:
        guard(refuse)
    assert excinfo.value.code == EXIT_REFUSED


def test_a_command_that_refuses_exits_two_and_says_why():
    @main.command("boom")
    def boom() -> None:
        guard(lambda: (_ for _ in ()).throw(PolicyError("no room", rule="loading.density")))

    result = run("boom")
    assert result.exit_code == EXIT_REFUSED
    assert "loading.density" in result.output
    main.commands.pop("boom")


def test_an_unknown_command_is_a_usage_error():
    result = run("nothing-like-that")
    assert result.exit_code != 0


def test_the_group_is_a_click_group():
    assert isinstance(main, click.Group)


def test_the_guarded_decorator_turns_a_refusal_into_an_exit_code():
    from hatchlot.cli.main import guarded

    @main.command("guarded-boom")
    @guarded
    def boom() -> None:
        raise PolicyError("no room", rule="loading.density")

    result = run("guarded-boom")
    assert result.exit_code == EXIT_REFUSED
    assert "loading.density" in result.output
    main.commands.pop("guarded-boom")


def test_the_guarded_decorator_lets_a_bug_through():
    from hatchlot.cli.main import guarded

    @guarded
    def broken() -> None:
        raise RuntimeError("that was not meant to happen")

    with pytest.raises(RuntimeError):
        broken()


def test_the_guarded_decorator_keeps_the_command_name_and_help():
    from hatchlot.cli.main import guarded

    @guarded
    def named() -> None:
        """What this command does."""

    assert named.__name__ == "named"
    assert named.__doc__ == "What this command does."


def test_the_traceback_flag_lets_the_real_error_through():
    from hatchlot.cli.main import guarded

    @main.command("traceback-boom")
    @guarded
    def boom() -> None:
        raise PolicyError("no room", rule="loading.density")

    quiet_result = run("traceback-boom")
    assert quiet_result.exit_code == EXIT_REFUSED
    loud_result = CliRunner().invoke(main, ["--traceback", "traceback-boom"])
    assert isinstance(loud_result.exception, PolicyError)
    main.commands.pop("traceback-boom")


def test_the_traceback_flag_is_off_by_default():
    assert Context().traceback is False


def test_the_context_carries_the_traceback_flag_down():
    from hatchlot.cli.main import pass_context, wants_traceback

    seen = []

    @main.command("traceback-check")
    @pass_context
    def check(context: Context) -> None:
        seen.append((context.traceback, wants_traceback()))

    run("traceback-check")
    CliRunner().invoke(main, ["--traceback", "traceback-check"])
    assert seen == [(False, False), (True, True)]
    main.commands.pop("traceback-check")


def test_wants_traceback_is_false_with_no_context_at_all():
    from hatchlot.cli.main import wants_traceback

    assert wants_traceback() is False
