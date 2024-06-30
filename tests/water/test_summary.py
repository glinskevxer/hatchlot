from decimal import Decimal

from hatchlot.calendar import DateRange
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.water import summarise
from hatchlot.water.monitoring import MonitoringLog, Reading, Thresholds
from hatchlot.water.source import SourceKind, SourceRegister, WaterSource
from hatchlot.water.summary import SupplyState


def sources(*specs):
    register = SourceRegister()
    for code, flow, kind in specs:
        register.add(
            WaterSource(code=code, name=code, kind=kind, design_flow=Quantity(flow, "gpm"))
        )
    return register


def reading(stamp, container="RW-1", celsius="10", oxygen="9"):
    return Reading(stamp, container, Temperature(celsius, "C"), oxygen)


SPRING = ("SP-1", 1000, SourceKind.SPRING)
REUSE = ("RU-1", 200, SourceKind.REUSE)


def test_a_station_with_water_to_spare_reads_comfortable():
    summary = summarise(sources(SPRING), MonitoringLog(), committed=Quantity(500, "gpm"))
    assert summary.state is SupplyState.COMFORTABLE
    assert summary.headroom == Quantity(500, "gpm")


def test_a_station_inside_a_tenth_of_its_supply_reads_tight():
    summary = summarise(sources(SPRING), MonitoringLog(), committed=Quantity(950, "gpm"))
    assert summary.state is SupplyState.TIGHT


def test_a_station_committed_past_its_supply_reads_short():
    summary = summarise(sources(SPRING), MonitoringLog(), committed=Quantity(1200, "gpm"))
    assert summary.state is SupplyState.SHORT
    assert summary.headroom == Quantity(-200, "gpm")


def test_a_station_with_no_water_is_short_whatever_it_committed():
    assert summarise(SourceRegister(), MonitoringLog()).state is SupplyState.SHORT


def test_nothing_committed_is_the_default():
    summary = summarise(sources(SPRING), MonitoringLog())
    assert summary.committed_flow == Quantity(0, "gpm")


def test_the_reuse_fraction_comes_through_from_the_register():
    summary = summarise(sources(SPRING, REUSE), MonitoringLog())
    assert summary.reuse_fraction.quantize(Decimal("0.001")) == Decimal("0.167")


def test_a_station_with_no_readings_has_no_mean_temperature():
    summary = summarise(sources(SPRING), MonitoringLog())
    assert summary.mean_temperature is None
    assert summary.units_monitored == 0
    assert not summary.has_open_excursions


def test_the_mean_temperature_is_over_the_readings_in_the_window():
    log = MonitoringLog(
        [
            reading("2024-09-01 08:00", celsius="10"),
            reading("2024-09-02 08:00", celsius="12"),
            reading("2024-10-01 08:00", celsius="20"),
        ]
    )
    summary = summarise(sources(SPRING), log, window=DateRange("2024-09-01", "2024-09-30"))
    assert summary.mean_temperature == Temperature(11, "C")


def test_excursions_outside_the_window_are_not_this_report_s_problem():
    log = MonitoringLog(
        [reading("2024-09-01 08:00", oxygen="4"), reading("2024-10-01 08:00", oxygen="4")]
    )
    summary = summarise(sources(SPRING), log, window=DateRange("2024-09-01", "2024-09-30"))
    assert len(summary.open_excursions) == 1
    assert summary.has_open_excursions


def test_the_whole_log_is_used_when_no_window_is_given():
    log = MonitoringLog(
        [
            reading("2024-09-01 08:00", oxygen="4"),
            reading("2024-10-01 08:00", container="RW-2", oxygen="4"),
        ]
    )
    summary = summarise(sources(SPRING), log)
    assert len(summary.open_excursions) == 2
    assert summary.units_monitored == 2


def test_the_thresholds_can_be_the_station_s_own():
    log = MonitoringLog([reading("2024-09-01 08:00", oxygen="6.5")])
    tighter = Thresholds(minimum_oxygen_mgL=Decimal(7))
    assert not summarise(sources(SPRING), log).has_open_excursions
    assert summarise(sources(SPRING), log, thresholds=tighter).has_open_excursions


def test_the_headline_line_says_the_state_and_the_counts():
    log = MonitoringLog([reading("2024-09-01 08:00", oxygen="4")])
    summary = summarise(sources(SPRING), log, committed=Quantity(500, "gpm"))
    line = summary.line()
    assert line.startswith("comfortable")
    assert "1 excursions" in line
    assert "1 units monitored" in line
