from dataclasses import dataclass

import pytest

from hatchlot.errors import DuplicateError, NotFoundError, ValidationError
from hatchlot.registry import CodeRegistry


@dataclass(frozen=True)
class Thing:
    code: str
    size: int = 1


def registry(*things):
    register: CodeRegistry[Thing] = CodeRegistry("thing", lambda thing: thing.code)
    for thing in things:
        register.add(thing)
    return register


def test_a_register_knows_what_it_holds():
    assert registry().kind == "thing"


def test_a_record_goes_in_under_its_normalised_code():
    register = registry(Thing(" rw 1 "))
    assert register.codes() == ("RW-1",)
    assert register.get("RW-1").code == " rw 1 "


def test_a_second_record_on_one_code_is_refused():
    register = registry(Thing("RW-1"))
    with pytest.raises(DuplicateError) as excinfo:
        register.add(Thing("rw 1"))
    assert excinfo.value.kind == "thing"


def test_a_missing_record_raises_by_kind_and_key():
    register = registry()
    with pytest.raises(NotFoundError) as excinfo:
        register.get("RW-9")
    assert excinfo.value.kind == "thing"
    assert excinfo.value.key == "RW-9"


def test_find_answers_none_where_get_raises():
    register = registry(Thing("RW-1"))
    assert register.find("RW-1") is not None
    assert register.find("RW-9") is None


def test_replacing_needs_the_record_to_be_there_already():
    register = registry(Thing("RW-1", size=1))
    register.replace(Thing("RW-1", size=5))
    assert register.get("RW-1").size == 5
    with pytest.raises(NotFoundError):
        register.replace(Thing("RW-9"))


def test_removing_takes_it_out_and_refuses_a_second_time():
    register = registry(Thing("RW-1"))
    assert register.remove("rw 1").code == "RW-1"
    assert len(register) == 0
    with pytest.raises(NotFoundError):
        register.remove("RW-1")


def test_listing_is_in_code_order_whatever_order_things_went_in():
    register = registry(Thing("RW-2"), Thing("RW-1"), Thing("RW-10"))
    assert [thing.code for thing in register] == ["RW-1", "RW-10", "RW-2"]


def test_a_filter_keeps_the_order():
    register = registry(Thing("RW-2", size=5), Thing("RW-1", size=1), Thing("RW-3", size=9))
    assert [thing.code for thing in register.where(lambda thing: thing.size > 1)] == [
        "RW-2",
        "RW-3",
    ]


def test_membership_takes_the_sloppy_form_and_rejects_a_non_code():
    register = registry(Thing("RW-1"))
    assert "rw 1" in register
    assert "RW-9" not in register
    assert 7 not in register
    assert "!!" not in register


def test_a_junk_code_is_still_refused_on_the_way_in():
    register: CodeRegistry[Thing] = CodeRegistry("thing", lambda thing: thing.code)
    with pytest.raises(ValidationError):
        register.add(Thing("  "))
