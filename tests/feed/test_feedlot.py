from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.feed.feedlot import (
    Analysis,
    FeedForm,
    FeedLot,
    energy_of,
    pellet_for,
    protein_of,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity


def analysis(protein="0.45", fat="0.16", fibre="0.02", ash="0.08", moisture="0.09"):
    return Analysis(
        protein=Decimal(protein),
        fat=Decimal(fat),
        fibre=Decimal(fibre),
        ash=Decimal(ash),
        moisture=Decimal(moisture),
    )


def feed_lot(code="FL-001", pellet="2.0", kilograms="1000", made="2025-01-10", months=6):
    return FeedLot(
        code=code,
        product="starter 45/16",
        form=FeedForm.CRUMBLE,
        pellet_mm=Decimal(pellet),
        analysis=analysis(),
        made_on=date.fromisoformat(made),
        quantity=Quantity(kilograms, "kg"),
        shelf_months=months,
    )


def test_the_analysis_adds_up_and_leaves_carbohydrate_behind():
    tag = analysis()
    assert tag.total == Decimal("0.80")
    assert tag.carbohydrate == Decimal("0.20")
    assert tag.dry_matter == Decimal("0.91")


def test_an_analysis_that_adds_to_more_than_the_feed_is_refused():
    with pytest.raises(ValidationError):
        analysis(protein="0.9", fat="0.5")


@pytest.mark.parametrize("bad", ["-0.1", "1.1"])
def test_a_fraction_outside_the_feed_is_refused(bad):
    with pytest.raises(ValidationError):
        analysis(protein=bad)


def test_the_digestible_energy_of_a_typical_salmon_feed():
    assert quantize(analysis().digestible_energy, 2) == Decimal("16.30")


def test_a_fattier_feed_carries_more_energy():
    lean = Analysis(
        protein=Decimal("0.45"),
        fat=Decimal("0.10"),
        fibre=Decimal("0.02"),
        ash=Decimal("0.08"),
        moisture=Decimal("0.09"),
    )
    assert analysis().digestible_energy > lean.digestible_energy


def test_a_feed_lot_normalises_its_code_and_needs_a_product():
    assert feed_lot(code=" fl 001 ").code == "FL-001"
    with pytest.raises(ValidationError):
        FeedLot(
            code="FL-1",
            product="  ",
            form=FeedForm.PELLET,
            pellet_mm=Decimal(3),
            analysis=analysis(),
            made_on=date(2025, 1, 10),
            quantity=Quantity(100, "kg"),
        )


def test_an_impossible_pellet_or_shelf_life_is_refused():
    with pytest.raises(ValidationError):
        feed_lot(pellet="0")
    with pytest.raises(ValidationError):
        feed_lot(pellet="40")
    with pytest.raises(ValidationError):
        feed_lot(months=0)


def test_a_form_that_is_not_a_form_is_refused():
    with pytest.raises(ValidationError):
        FeedLot(
            code="FL-1",
            product="starter",
            form="pellet",  # type: ignore[arg-type]
            pellet_mm=Decimal(3),
            analysis=analysis(),
            made_on=date(2025, 1, 10),
            quantity=Quantity(100, "kg"),
        )


def test_extruded_feed_is_the_kind_that_floats():
    assert FeedForm.EXTRUDED.floats
    assert not FeedForm.CRUMBLE.floats


def test_the_expiry_runs_off_the_manufacture_date():
    lot = feed_lot(made="2025-01-10", months=6)
    assert lot.expires_on == date(2025, 7, 10)
    assert not lot.is_expired("2025-07-10")
    assert lot.is_expired("2025-07-11")
    assert lot.days_left("2025-07-01") == 9


def test_expired_or_empty_feed_is_refused_by_name():
    old = feed_lot(made="2024-01-10")
    with pytest.raises(PolicyError) as excinfo:
        old.check_usable("2025-01-10")
    assert excinfo.value.rule == "feed.expired"
    empty = feed_lot(kilograms="0")
    with pytest.raises(PolicyError) as excinfo:
        empty.check_usable("2025-02-01")
    assert excinfo.value.rule == "feed.empty"


def test_good_feed_passes_the_check_quietly():
    feed_lot().check_usable("2025-02-01")


def test_the_pellet_has_to_suit_the_fish():
    lot = feed_lot(pellet="2.0")
    assert lot.suits(Quantity(60, "mm"))
    assert not lot.suits(Quantity(200, "mm"))
    assert not lot.suits(Quantity(20, "mm"))


def test_a_fish_of_no_length_is_refused():
    with pytest.raises(ValidationError):
        feed_lot().suits(Quantity(0, "mm"))


def test_drawing_feed_out_and_putting_it_back():
    lot = feed_lot(kilograms="1000")
    assert lot.draw(Quantity(250, "kg")) == Quantity(750, "kg")
    assert lot.receive(Quantity(50, "kg")) == Quantity(800, "kg")


def test_drawing_more_than_the_lot_holds_is_refused():
    lot = feed_lot(kilograms="100")
    with pytest.raises(ValidationError):
        lot.draw(Quantity(200, "kg"))


def test_a_negative_draw_or_receipt_is_refused():
    lot = feed_lot()
    with pytest.raises(ValidationError):
        lot.draw(Quantity(-1, "kg"))
    with pytest.raises(ValidationError):
        lot.receive(Quantity(-1, "kg"))


def test_the_energy_and_protein_in_a_quantity_of_feed():
    lot = feed_lot()
    assert quantize(energy_of(lot, Quantity(100, "kg")), 1) == Decimal("1630.0")
    assert protein_of(lot, Quantity(100, "kg")) == Quantity("45.00", "kg")


def test_the_pellet_a_fish_of_a_length_wants():
    assert pellet_for(Quantity(100, "mm")) == Quantity("3.00", "mm")
    assert pellet_for(Quantity(100, "mm"), share="0.02") == Quantity("2.00", "mm")
    with pytest.raises(ValidationError):
        pellet_for(Quantity(0, "mm"))
    with pytest.raises(ValidationError):
        pellet_for(Quantity(100, "mm"), share="0.5")
