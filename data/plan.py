#!/usr/bin/env python3
"""Generate the synthetic 2026 plan and independent mixed-source expectations."""

import json
from collections import defaultdict
from pathlib import Path

from generate import source_rows


OUTPUT = Path(__file__).resolve().parent
# Values follow country/carrier loop order and intentionally vary across routes.
PLANNED_COUNTS = {
    "toy_train": (155, 290, 185, 225, 130, 175),
    "books": (80, 135, 115, 75, 65, 90),
    "plush": (125, 180, 105, 95, 150, 110),
}
TARGET_RATES = {
    "toy_train": (10, 8, 12, 11, 9, 12),
    "books": (8, 9, 7, 10, 6, 9),
    "plush": (9, 11, 10, 7, 8, 12),
}


def plan_documents():
    """Return one stable, uniquely identified plan per category and route."""
    documents = []
    for category in ("toy_train", "books", "plush"):
        for country_index, country in enumerate(("France", "Germany", "Spain")):
            for carrier_index, carrier in enumerate(("Reindeer Express", "Polar Parcel")):
                route = country_index * 2 + carrier_index
                planned = PLANNED_COUNTS[category][route]
                target = float(TARGET_RATES[category][route])
                identifier = f"{category}-{country}-{carrier}".lower().replace("_", "-").replace(" ", "-")
                documents.append({
                    "_id": identifier,
                    "_source": {
                        "gift_category": category,
                        "country": country,
                        "carrier": carrier,
                        "planned_deliveries": planned,
                        "target_late_rate": target,
                    },
                })
    return documents


def expected_results(documents, historical_rows):
    """Derive query expectations directly from synthetic records, without ES."""
    totals = defaultdict(int)
    plans = {}
    for document in documents:
        plan = document["_source"]
        totals[plan["gift_category"]] += plan["planned_deliveries"]
        plans[(plan["gift_category"], plan["carrier"], plan["country"])] = plan
    categories = [{"gift_category": category, "planned_deliveries": total}
                  for category, total in totals.items()]
    categories.sort(key=lambda row: (-row["planned_deliveries"], row["gift_category"]))
    groups = defaultdict(list)
    for row in historical_rows:
        if row["gift_category"] == "toy_train":
            groups[(row["gift_category"], row["carrier"], row["country"])].append(row)
    joined = []
    for key, rows in groups.items():
        plan = plans[key]
        total = len(rows)
        late = sum(row["delay_minutes"] > 0 for row in rows)
        joined.append({
            "carrier": key[1],
            "country": key[2],
            "historical_total": total,
            "historical_late": late,
            "historical_late_rate": 100.0 * late / total,
            "planned_deliveries": plan["planned_deliveries"],
            "target_late_rate": plan["target_late_rate"],
            "late_rate_gap": 100.0 * late / total - plan["target_late_rate"],
            "illustrative_late_deliveries": 1.0 * plan["planned_deliveries"] * late / total,
        })
    joined.sort(key=lambda row: (-row["historical_late_rate"], row["carrier"], row["country"]))
    return {"04-planned-volumes": categories, "05-archive-plan-join": joined}


def main():
    documents = plan_documents()
    expected = expected_results(documents, source_rows())
    (OUTPUT / "delivery-plan.json").write_text(json.dumps(documents, indent=2) + "\n")
    (OUTPUT / "plan-expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    total = sum(document["_source"]["planned_deliveries"] for document in documents)
    print(f"Generated {len(documents)} route plans for 2026; {total} planned deliveries.")


if __name__ == "__main__":
    main()
