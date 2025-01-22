from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.health.biosecurity import (
    Zone,
    ZoneClass,
    ZoneMap,
    contact_score,
    equipment_rule,
    reuse_downstream,
    zone_of,
)


def zone(code, zone_class, reuse="0", source="SP-1"):
    return Zone(code=code, zone_class=zone_class, water_source=source, reuse_share=Decimal(reuse))


def station():
    plan = ZoneMap()
    plan.add(zone("Z-BROOD", ZoneClass.BROODSTOCK))
    plan.add(zone("Z-NURSE", ZoneClass.NURSERY))
    plan.add(zone("Z-PROD", ZoneClass.PRODUCTION, reuse="0.4"))
    plan.add(zone("Z-QUAR", ZoneClass.QUARANTINE, reuse="0.8"))
    return plan


def test_the_ranks_run_from_the_dirtiest_to_the_cleanest():
    ranks = [
        ZoneClass.ISOLATION.rank,
        ZoneClass.QUARANTINE.rank,
        ZoneClass.PRODUCTION.rank,
        ZoneClass.BROODSTOCK.rank,
    ]
    assert ranks == sorted(ranks)
    assert ZoneClass.QUARANTINE.is_restricted
    assert not ZoneClass.PRODUCTION.is_restricted


def test_a_zone_normalises_its_codes_and_checks_its_reuse_share():
    entry = zone(" z prod ", ZoneClass.PRODUCTION, reuse="0.5", source=" sp 1 ")
    assert entry.code == "Z-PROD"
    assert entry.water_source == "SP-1"
    with pytest.raises(ValidationError):
        zone("Z-1", ZoneClass.PRODUCTION, reuse="1.5")
    with pytest.raises(ValidationError):
        Zone(code="Z-1", zone_class="production")  # type: ignore[arg-type]


def test_first_use_water_is_the_zone_with_no_reuse():
    assert zone("Z-1", ZoneClass.PRODUCTION).is_first_use
    assert not zone("Z-1", ZoneClass.PRODUCTION, reuse="0.1").is_first_use


def test_the_direction_of_a_movement():
    plan = station()
    assert plan.direction("Z-PROD", "Z-BROOD") == "uphill"
    assert plan.direction("Z-BROOD", "Z-PROD") == "downhill"
    assert plan.direction("Z-PROD", "Z-PROD") == "across"


def test_a_lot_with_an_open_case_does_not_move_at_all():
    plan = station()
    with pytest.raises(PolicyError) as excinfo:
        plan.check_movement("Z-NURSE", "Z-PROD", lot_has_open_case=True)
    assert excinfo.value.rule == "biosecurity.open_case"


def test_the_case_rule_bites_before_the_others_do():
    plan = station()
    with pytest.raises(PolicyError) as excinfo:
        plan.check_movement("Z-PROD", "Z-PROD", lot_has_open_case=True)
    assert excinfo.value.rule == "biosecurity.open_case"


def test_reused_water_cannot_feed_a_first_use_zone():
    plan = station()
    with pytest.raises(PolicyError) as excinfo:
        plan.check_movement("Z-PROD", "Z-NURSE", disinfected=True)
    assert excinfo.value.rule == "biosecurity.water"


def test_nothing_leaves_a_restricted_zone():
    plan = station()
    with pytest.raises(PolicyError) as excinfo:
        plan.check_movement("Z-QUAR", "Z-PROD", disinfected=True)
    assert excinfo.value.rule == "biosecurity.restricted"


def test_uphill_needs_the_equipment_disinfected():
    plan = ZoneMap()
    plan.add(zone("Z-PROD", ZoneClass.PRODUCTION))
    plan.add(zone("Z-BROOD", ZoneClass.BROODSTOCK))
    with pytest.raises(PolicyError) as excinfo:
        plan.check_movement("Z-PROD", "Z-BROOD")
    assert excinfo.value.rule == "biosecurity.uphill"
    plan.check_movement("Z-PROD", "Z-BROOD", disinfected=True)


def test_downhill_is_free():
    plan = ZoneMap()
    plan.add(zone("Z-PROD", ZoneClass.PRODUCTION))
    plan.add(zone("Z-BROOD", ZoneClass.BROODSTOCK))
    plan.check_movement("Z-BROOD", "Z-PROD")


def test_a_movement_within_one_zone_is_always_allowed():
    station().check_movement("Z-QUAR", "Z-QUAR")


def test_the_yes_or_no_form_of_the_same_question():
    plan = station()
    assert not plan.may_move("Z-QUAR", "Z-PROD")
    assert plan.may_move("Z-BROOD", "Z-PROD")


def test_where_a_lot_could_go_today():
    plan = station()
    assert plan.destinations_from("Z-QUAR") == ()
    assert "Z-PROD" in plan.destinations_from("Z-BROOD")


def test_the_restricted_zones_and_the_zones_on_a_source():
    plan = station()
    assert [entry.code for entry in plan.restricted_zones()] == ["Z-QUAR"]
    assert len(plan.on_source("sp 1")) == 4


def test_what_has_to_happen_to_a_net():
    plan = station()
    prod = plan.get("Z-PROD")
    brood = plan.get("Z-BROOD")
    quar = plan.get("Z-QUAR")
    assert equipment_rule(prod, prod) == "nothing"
    assert equipment_rule(quar, prod) == "dedicated"
    assert equipment_rule(prod, brood) == "disinfect"
    assert equipment_rule(brood, prod) == "rinse"


def test_the_contact_score_counts_the_zones_that_can_reach_one():
    plan = station()
    assert contact_score(plan, "Z-PROD") >= Decimal(1)
    assert contact_score(plan, "Z-QUAR") >= Decimal(0)


def test_which_zone_a_container_sits_in():
    plan = station()
    layout = {"RW-1": "Z-PROD", "TK-1": "Z-NURSE"}
    assert zone_of(plan, "rw 1", layout).code == "Z-PROD"
    with pytest.raises(ValidationError):
        zone_of(plan, "RW-9", layout)


def test_the_zones_carrying_too_much_reused_water():
    plan = station()
    assert [entry.code for entry in reuse_downstream(plan)] == ["Z-QUAR"]
    assert len(reuse_downstream(plan, "0.1")) == 2
    with pytest.raises(ValidationError):
        reuse_downstream(plan, "-0.1")
