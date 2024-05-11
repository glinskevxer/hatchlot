from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.station import DEFAULT_PROFILE, StationProfile
from hatchlot.units import System


def test_a_profile_normalises_its_own_code_and_trims_its_name():
    profile = StationProfile(code=" cold creek ", name="  Cold Creek Hatchery ")
    assert profile.code == "COLD-CREEK"
    assert profile.name == "Cold Creek Hatchery"


def test_the_default_profile_is_a_us_station_starting_in_july():
    assert DEFAULT_PROFILE.system is System.US
    assert DEFAULT_PROFILE.brood_start_month == 7
    assert not DEFAULT_PROFILE.is_metric


def test_a_nameless_station_is_refused():
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="   ")


def test_a_system_that_is_not_a_system_is_refused():
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", system="us")  # type: ignore[arg-type]


@pytest.mark.parametrize("month", [0, 13, -1])
def test_an_impossible_brood_start_month_is_refused(month):
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", brood_start_month=month)


@pytest.mark.parametrize("elevation", ["-600", "5000"])
def test_an_elevation_no_hatchery_sits_at_is_refused(elevation):
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", elevation_m=Decimal(elevation))


def test_a_tolerance_over_half_is_not_a_tolerance():
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", loading_tolerance=Decimal("0.6"))
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", inventory_tolerance=Decimal("0.6"))


def test_a_mortality_alert_of_zero_would_fire_on_everything():
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", mortality_alert=Decimal(0))


@pytest.mark.parametrize("places", [-1, 7])
def test_an_unprintable_number_of_places_is_refused(places):
    with pytest.raises(ValidationError):
        StationProfile(code="X", name="X", report_places=places)


def test_switching_system_keeps_everything_else():
    profile = StationProfile(code="X", name="X", elevation_m=Decimal(500))
    metric = profile.with_system(System.METRIC)
    assert metric.is_metric
    assert metric.elevation_m == Decimal(500)
    assert profile.system is System.US


def test_a_profile_round_trips_through_storage():
    profile = StationProfile(
        code="cold-creek",
        name="Cold Creek",
        system=System.METRIC,
        brood_start_month=9,
        elevation_m=Decimal("812.5"),
        report_places=3,
    )
    assert StationProfile.from_dict(profile.to_dict()) == profile


def test_from_dict_fills_in_every_default():
    profile = StationProfile.from_dict({"code": "x", "name": "X"})
    assert profile == StationProfile(code="X", name="X")


def test_from_dict_takes_a_system_object_as_well_as_its_value():
    assert StationProfile.from_dict({"code": "x", "name": "X", "system": System.METRIC}).is_metric


def test_a_typo_in_a_settings_file_is_refused_rather_than_ignored():
    with pytest.raises(ValidationError) as excinfo:
        StationProfile.from_dict({"code": "x", "name": "X", "loading_tolerence": "0.1"})
    assert "loading_tolerence" in str(excinfo.value)


@pytest.mark.parametrize("missing", ["code", "name"])
def test_a_profile_without_its_identity_is_refused(missing):
    raw = {"code": "x", "name": "X"}
    del raw[missing]
    with pytest.raises(ValidationError):
        StationProfile.from_dict(raw)


def test_an_unknown_system_value_is_refused_by_name():
    with pytest.raises(ValidationError) as excinfo:
        StationProfile.from_dict({"code": "x", "name": "X", "system": "imperial"})
    assert "imperial" in str(excinfo.value)
