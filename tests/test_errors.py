import pytest

from hatchlot.errors import (
    ConversionError,
    DuplicateError,
    HatchlotError,
    NotFoundError,
    PolicyError,
    StateError,
    UnitError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc",
    [
        ValidationError("bad"),
        UnitError("bad"),
        ConversionError("bad"),
        NotFoundError("lot", "L-1"),
        DuplicateError("lot", "L-1"),
        StateError("bad"),
        PolicyError("bad", rule="r"),
    ],
)
def test_everything_deliberate_is_one_family(exc):
    assert isinstance(exc, HatchlotError)


def test_validation_error_prefixes_the_field_when_it_has_one():
    assert str(ValidationError("must be positive", field="flow")) == "flow: must be positive"
    assert str(ValidationError("must be positive")) == "must be positive"


def test_unit_error_is_a_validation_error_so_one_handler_catches_both():
    assert isinstance(UnitError("no such unit"), ValidationError)


def test_not_found_carries_the_lookup_that_failed():
    err = NotFoundError("container", "RW-3")
    assert err.kind == "container"
    assert err.key == "RW-3"
    assert "RW-3" in str(err)


def test_duplicate_carries_the_key_that_was_taken():
    err = DuplicateError("lot", "2024-CHK-01")
    assert err.key == "2024-CHK-01"
    assert "already exists" in str(err)


def test_policy_error_prints_the_rule_that_refused():
    err = PolicyError("density index over limit", rule="loading.density")
    assert err.rule == "loading.density"
    assert str(err) == "[loading.density] density index over limit"


def test_policy_error_is_not_a_state_error():
    assert not isinstance(PolicyError("x", rule="r"), StateError)
