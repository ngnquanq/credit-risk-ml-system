#!/usr/bin/env python3
"""Synthetic UAT personas (E16): 200 applications with fake identity fields.

Feature values are sampled from simple distributions shaped like the Kaggle marginals; no
Kaggle row and no real person is ever shown in the portals. Output is the JSON body for
POST /api/v1/applications, one per line, so a UAT script can submit them with tester tokens.

    python scripts/uat/seed_personas.py --count 200 --seed 7 > reports/uat/personas.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta

INCOME_TYPES = ["Working", "Commercial associate", "Pensioner", "State servant"]
EDUCATION = ["Secondary / secondary special", "Higher education", "Incomplete higher", "Lower secondary"]
FAMILY = ["Married", "Single / not married", "Civil marriage", "Separated", "Widow"]
HOUSING = ["House / apartment", "With parents", "Rented apartment", "Municipal apartment"]


def persona(rng: random.Random, index: int, today: date) -> dict:
    age_years = rng.randint(21, 65)
    income_type = rng.choices(INCOME_TYPES, weights=[52, 23, 18, 7])[0]
    employed = income_type != "Pensioner"
    annual_income = round(rng.lognormvariate(12.0, 0.5), -3)
    credit = round(annual_income * rng.uniform(0.5, 4.0), -4)
    start = today - timedelta(days=rng.randint(60, 365 * 15)) if employed else None
    return {
        # Ids outside the Kaggle range so no real history is joined by accident.
        "sk_id_curr": f"UAT{index:05d}",
        "birth_date": (today - timedelta(days=age_years * 365 + rng.randint(0, 364))).isoformat(),
        "cnt_children": rng.choices([0, 1, 2, 3], weights=[70, 20, 8, 2])[0],
        "amt_income_total": annual_income,
        "amt_credit": credit,
        "amt_goods_price": round(credit * rng.uniform(0.8, 1.0), -4),
        "name_income_type": income_type,
        "name_education_type": rng.choices(EDUCATION, weights=[71, 24, 3, 2])[0],
        "name_family_status": rng.choices(FAMILY, weights=[64, 15, 10, 6, 5])[0],
        "name_housing_type": rng.choices(HOUSING, weights=[89, 5, 4, 2])[0],
        "employment_start_date": start.isoformat() if start else None,
        "bureau_consent": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    today = date.today()
    for i in range(1, args.count + 1):
        print(json.dumps(persona(rng, i, today), ensure_ascii=False))


if __name__ == "__main__":
    main()
