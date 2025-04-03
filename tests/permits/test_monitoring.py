from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.permits.limits import Basis, Limit, Parameter, Sample
from hatchlot.permits.monitoring import (
    MonitoringRecord,
    Reading,
    compliance_share,
    exceedance_days,
    next_due,
    worst_exceedance,
)
from hatchlot.quantities.base import Quantity

MARCH = DateRange("2025-03-01", "2025-03-31")


def limit(value="5", basis=Basis.CONCENTRATION):
    return Limit(parameter=Parameter.SUSPENDED_SOLIDS, basis=basis, value=Decimal(value))


def reading(
    day, outfall="OF-1", intake="2", outfall_value="6", parameter=Parameter.SUSPENDED_SOLIDS
):
    return Reading(
        day=date.fromisoformat(day),
        outfall=outfall,
        sample=Sample(
            parameter=parameter,
            intake=Decimal(intake),
            outfall=Decimal(outfall_value),
            flow=Quantity(1000, "Lpm"),
        ),
        taken_by="kt",
    )


def record(*readings):
    book = MonitoringRecord()
    for entry in readings:
        book.record(entry)
    return book


def test_a_reading_normalises_its_outfall_and_needs_a_person():
    entry = reading("2025-03-01", outfall=" of 1 ")
    assert entry.outfall == "OF-1"
    assert entry.parameter is Parameter.SUSPENDED_SOLIDS
    with pytest.raises(ValidationError):
        Reading(
            day=date(2025, 3, 1),
            outfall="OF-1",
            sample=Sample(parameter=Parameter.BOD, intake=Decimal(1), outfall=Decimal(2)),
            taken_by=" ",
        )


def test_readings_slice_by_outfall_and_by_parameter():
    book = record(
        reading("2025-03-01", outfall="OF-1"),
        reading("2025-03-02", outfall="OF-2"),
        reading("2025-03-03", parameter=Parameter.BOD),
    )
    assert book.outfalls() == ("OF-1", "OF-2")
    assert len(book.for_outfall("of 1")) == 2
    assert len(book.for_parameter(Parameter.BOD)) == 1
    assert len(book.for_parameter(Parameter.SUSPENDED_SOLIDS, MARCH)) == 2


def test_a_sample_over_the_daily_maximum_is_an_exceedance():
    book = record(reading("2025-03-01", intake="2", outfall_value="10"))
    found = book.daily_exceedances(limit(value="5"))
    assert len(found) == 1
    assert found[0].value == Decimal(8)
    assert found[0].over_by == Decimal(3)
    assert found[0].share == Decimal("1.6")


def test_a_clean_month_has_no_exceedances():
    book = record(reading("2025-03-01", intake="2", outfall_value="5"))
    assert book.daily_exceedances(limit(value="5")) == ()


def test_a_month_can_pass_every_day_and_fail_the_average():
    book = record(
        reading("2025-03-01", intake="0", outfall_value="4"),
        reading("2025-03-08", intake="0", outfall_value="4"),
        reading("2025-03-15", intake="0", outfall_value="4"),
    )
    daily = limit(value="5")
    monthly = limit(value="3")
    assert book.daily_exceedances(daily) == ()
    assert book.average_for(monthly, MARCH) == Decimal(4)
    assert book.average_exceeds(monthly, MARCH)


def test_a_month_can_fail_a_day_and_pass_the_average():
    book = record(
        reading("2025-03-01", intake="0", outfall_value="12"),
        *[reading(f"2025-03-{day:02d}", intake="0", outfall_value="1") for day in range(2, 12)],
    )
    assert len(book.daily_exceedances(limit(value="5"))) == 1
    assert not book.average_exceeds(limit(value="5"), MARCH)


def test_an_average_over_a_window_with_no_samples_is_refused():
    with pytest.raises(ValidationError):
        MonitoringRecord().average_for(limit(), MARCH)


def test_the_sampling_frequency_is_counted_over_the_window():
    book = record(*[reading(f"2025-03-{day:02d}") for day in (1, 8, 15, 22)])
    assert book.sample_count(Parameter.SUSPENDED_SOLIDS, MARCH) == 4
    assert book.is_frequency_met(Parameter.SUSPENDED_SOLIDS, MARCH, per_month=4)
    assert not book.is_frequency_met(Parameter.SUSPENDED_SOLIDS, MARCH, per_month=8)
    with pytest.raises(ValidationError):
        book.is_frequency_met(Parameter.SUSPENDED_SOLIDS, MARCH, per_month=0)


def test_the_worst_exceedance_is_the_biggest_share_not_the_biggest_number():
    book = record(
        reading("2025-03-01", intake="0", outfall_value="12"),
        reading("2025-03-02", intake="0", outfall_value="7"),
    )
    tight = limit(value="5")
    found = book.daily_exceedances(tight)
    worst = worst_exceedance(found)
    assert worst is not None
    assert worst.value == Decimal(12)
    assert worst_exceedance(()) is None


def test_how_many_days_had_an_exceedance():
    book = record(
        reading("2025-03-01", intake="0", outfall_value="12", outfall="OF-1"),
        reading("2025-03-01", intake="0", outfall_value="12", outfall="OF-2"),
        reading("2025-03-05", intake="0", outfall_value="12"),
    )
    found = book.daily_exceedances(limit(value="5"))
    assert len(found) == 3
    assert exceedance_days(found) == 2


def test_the_share_of_samples_inside_a_limit():
    book = record(
        reading("2025-03-01", intake="0", outfall_value="4"),
        reading("2025-03-02", intake="0", outfall_value="12"),
    )
    assert compliance_share(book, limit(value="5"), MARCH) == Decimal("0.5")
    with pytest.raises(ValidationError):
        compliance_share(MonitoringRecord(), limit(), MARCH)


def test_a_mass_limit_is_read_against_the_flow():
    book = record(reading("2025-03-01", intake="0", outfall_value="6"))
    found = book.daily_exceedances(limit(value="5", basis=Basis.MASS_PER_DAY))
    assert len(found) == 1


def test_when_the_next_sample_falls_due():
    book = record(reading("2025-03-01"))
    assert next_due(book, "OF-1") == date(2025, 3, 8)
    assert next_due(book, "OF-9") is None
    with pytest.raises(ValidationError):
        next_due(book, "OF-1", interval_days=0)
