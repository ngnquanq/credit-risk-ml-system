"""DAYS_EMPLOYED at serving matches the training convention (E2 AC4, finding F-01)."""

from datetime import date

import pytest

from flink.jobs.application_transforms import DAYS_EMPLOYED_NOT_EMPLOYED, days_employed

EPOCH_DAYS_2026_11_22 = (date(2026, 11, 22) - date(1970, 1, 1)).days


def test_employed_five_years_is_negative():
    assert days_employed("2021-11-22", "2026-11-22T09:12:03Z") == -1826


def test_started_on_application_day_is_zero():
    assert days_employed("2026-11-22", "2026-11-22T00:00:00Z") == 0


def test_debezium_epoch_days_are_supported():
    assert days_employed(str(EPOCH_DAYS_2026_11_22 - 10), "2026-11-22T09:12:03Z") == -10


@pytest.mark.parametrize("start", [None, ""])
def test_no_employment_start_is_the_kaggle_sentinel(start):
    assert days_employed(start, "2026-11-22T09:12:03Z") == DAYS_EMPLOYED_NOT_EMPLOYED == 365243


@pytest.mark.parametrize("created", [None, "", "not a date"])
def test_missing_application_date_is_unknown(created):
    assert days_employed("2021-01-01", created) is None


def test_values_are_never_positive_unless_sentinel():
    for start in ("2000-01-01", "2020-06-30", "2026-11-21"):
        value = days_employed(start, "2026-11-22T09:12:03Z")
        assert value <= 0
