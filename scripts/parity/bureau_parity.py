"""Runs inside the Flink image: bureau features from the dbt mart (training side) against the UDF (serving side).

Input on stdin: {"ids": [...], "bureau": [...], "balance": [...], "mart": [...]} (see bureau_parity.sh).
Exit status 1 when any feature differs for any customer in the sample.
"""

import collections
import json
import math
import sys

sys.path.insert(0, "/opt/app/jobs")
import bureau_aggregation_udfs as udfs  # noqa: E402

data = json.load(sys.stdin)
bureau = collections.defaultdict(list)
for row in data["bureau"]:
    bureau[str(row["SK_ID_CURR"])].append({k.lower(): v for k, v in row.items()})
balance = collections.defaultdict(list)
for row in data["balance"]:
    balance[row["SK_ID_BUREAU"]].append({k.lower(): v for k, v in row.items()})
mart = {str(m["SK_ID_CURR"]): m for m in data["mart"]}


def same(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-9)
    except (TypeError, ValueError):
        return a == b


compared = customers_with_difference = 0
differences = collections.Counter()
kinds = collections.defaultdict(collections.Counter)
for customer in data["ids"]:
    row = mart.get(customer)
    if row is None:
        continue
    records = bureau.get(customer, [])
    rows = [m for r in records for m in balance.get(r["sk_id_bureau"], [])]
    features = udfs._transform_bureau_data(records, rows)
    compared += 1
    differs = False
    for name, value in row.items():
        if name == "SK_ID_CURR" or name not in features or same(value, features[name]):
            continue
        differs = True
        differences[name] += 1
        kinds[name]["dbt NULL" if value is None else ("UDF NULL" if features[name] is None else "different values")] += 1
    customers_with_difference += differs

columns = len([k for k in next(iter(mart.values())) if k != "SK_ID_CURR"]) if mart else 0
print(f"customers compared: {compared}; with a difference: {customers_with_difference}; columns that differ: {len(differences)} of {columns}")
for name, count in differences.most_common():
    print(f"  {name}: {count}/{compared}  {dict(kinds[name])}")
sys.exit(1 if differences or not compared else 0)
