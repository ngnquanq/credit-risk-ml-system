"""Bureau aggregation rules that the training side and the Flink job must agree on.

The dbt model mart_bureau_features had drifted from the UDF on these rules (limit guard, credits with balance,
no active credit, missing amounts). scripts/parity/bureau_parity.sh compares the two on the cluster; these tests
pin the rules themselves.
"""

import sys
import types


def _stub_pyflink():
    """The Flink image has PyFlink; a laptop or CI runner does not. The transform is plain Python, so stub the imports."""
    if "pyflink" in sys.modules:
        return
    pyflink = types.ModuleType("pyflink")
    table = types.ModuleType("pyflink.table")
    udf_mod = types.ModuleType("pyflink.table.udf")

    class DataTypes:
        @staticmethod
        def STRING():
            return "STRING"

    table.DataTypes = DataTypes
    udf_mod.udf = lambda *args, **kwargs: (lambda fn: fn)
    pyflink.table = table
    sys.modules.update({"pyflink": pyflink, "pyflink.table": table, "pyflink.table.udf": udf_mod})


_stub_pyflink()

from flink.jobs.bureau_aggregation_udfs import _transform_bureau_data as transform  # noqa: E402


def credit(bureau_id=1, active="Closed", credit=1000.0, debt=0.0, limit=0.0, **extra):
    return {"sk_id_bureau": bureau_id, "credit_active": active, "credit_type": "Consumer credit",
            "amt_credit_sum": credit, "amt_credit_sum_debt": debt, "amt_credit_sum_limit": limit,
            "amt_credit_sum_overdue": 0.0, **extra}


def month(bureau_id, status="0", months=-1):
    return {"sk_id_bureau": bureau_id, "months_balance": months, "status": status}


def test_zero_debt_against_zero_limit_is_not_maxed_out():
    f = transform([credit(1, limit=0.0, debt=0.0), credit(2, limit=0.0, debt=0.0)], [])
    assert f["BUREAU_MAXED_OUT_COUNT"] == 0 and f["BUREAU_HIGH_UTIL_COUNT"] == 0


def test_debt_at_the_limit_is_maxed_out_and_above_80_percent_is_high_use():
    f = transform([credit(1, limit=1000.0, debt=1000.0), credit(2, limit=1000.0, debt=900.0), credit(3, limit=1000.0, debt=100.0)], [])
    assert f["BUREAU_MAXED_OUT_COUNT"] == 1
    assert f["BUREAU_HIGH_UTIL_COUNT"] == 2
    assert f["BUREAU_MAXED_OUT_RATIO"] == 1 / 3


def test_credits_with_balance_counts_only_credits_that_have_balance_rows():
    bureau = [credit(1), credit(2), credit(3)]
    assert transform(bureau, [])["BUREAU_WITH_BALANCE_COUNT"] == 0
    assert transform(bureau, [month(1), month(1, months=-2), month(3)])["BUREAU_WITH_BALANCE_COUNT"] == 2


def test_no_active_credit_sums_are_zero_not_missing():
    f = transform([credit(1, active="Closed", credit=500.0, debt=100.0)], [])
    assert (f["BUREAU_ACTIVE_CREDIT_SUM"], f["BUREAU_ACTIVE_DEBT_SUM"], f["BUREAU_ACTIVE_OVERDUE_SUM"]) == (0.0, 0.0, 0.0)


def test_active_sums_add_up_only_active_credits():
    f = transform([credit(1, active="Active", credit=500.0, debt=100.0), credit(2, active="Closed", credit=900.0, debt=0.0)], [])
    assert f["BUREAU_ACTIVE_CREDIT_SUM"] == 500.0 and f["BUREAU_ACTIVE_DEBT_SUM"] == 100.0


def test_no_recorded_overdue_is_zero_as_in_the_training_dataset():
    assert transform([credit(1)], [])["BUREAU_AMT_MAX_OVERDUE_EVER"] == 0.0
    assert transform([], [])["BUREAU_AMT_MAX_OVERDUE_EVER"] == 0.0
    assert transform([credit(1, amt_credit_max_overdue=250.0), credit(2, amt_credit_max_overdue=80.0)], [])["BUREAU_AMT_MAX_OVERDUE_EVER"] == 250.0


def test_debt_to_credit_ratio_needs_a_credit_amount_and_treats_missing_debt_as_zero():
    assert transform([credit(1, credit=0.0, debt=50.0)], [])["BUREAU_DEBT_TO_CREDIT_RATIO"] is None
    assert transform([credit(1, credit=1000.0, debt=None)], [])["BUREAU_DEBT_TO_CREDIT_RATIO"] == 0.0
    assert transform([credit(1, credit=1000.0, debt=250.0)], [])["BUREAU_DEBT_TO_CREDIT_RATIO"] == 0.25
