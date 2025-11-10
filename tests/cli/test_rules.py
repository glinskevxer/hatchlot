import re
from pathlib import Path

from click.testing import CliRunner

import hatchlot
from hatchlot.cli import main
from hatchlot.cli.rules import RULES, rule_named

SOURCE = Path(hatchlot.__file__).parent
RULE_IN_CODE = re.compile(r'rule="([a-z_.]+)"')


def run(*args):
    return CliRunner().invoke(main, ["--quiet", *args])


def rules_in_code() -> set[str]:
    found: set[str] = set()
    for path in SOURCE.rglob("*.py"):
        found.update(RULE_IN_CODE.findall(path.read_text(encoding="utf-8")))
    return found


def test_every_rule_the_code_can_raise_is_in_the_list():
    listed = {rule.name for rule in RULES}
    for name in rules_in_code():
        assert name in listed, name


def test_every_listed_rule_is_one_the_code_can_actually_raise():
    raised = rules_in_code()
    for rule in RULES:
        if rule.name.startswith("loading."):
            continue
        assert rule.name in raised, rule.name


def test_the_list_is_sorted_and_has_no_repeats():
    names = [rule.name for rule in RULES]
    assert names == sorted(names)
    assert len(set(names)) == len(names)


def test_every_rule_says_what_it_means():
    for rule in RULES:
        assert rule.meaning.strip()
        assert rule.area.strip()


def test_a_rule_can_be_looked_up_by_the_name_a_refusal_printed():
    found = rule_named("incubation.tender")
    assert found is not None
    assert "handled" in found.meaning
    assert rule_named("nothing.like.that") is None


def test_the_rules_command_lists_them():
    result = run("rules")
    assert result.exit_code == 0
    assert "incubation.tender" in result.output
    assert "release.withdrawal" in result.output


def test_the_rules_can_be_narrowed_to_an_area():
    result = CliRunner().invoke(main, ["rules", "--area", "brood"])
    assert "cross.sire_share" in result.output
    assert "haul.tempering" not in result.output
    assert "rules" in result.output


def test_an_area_that_does_not_exist_lists_nothing():
    assert "0 rules" in CliRunner().invoke(main, ["rules", "--area", "nothing"]).output
