#!/usr/bin/env python3
"""Generate the deterministic archive and independent ES|QL expectations."""

import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SEED = 20251225
# Each category lists (deliveries, late deliveries) in country/carrier loop order.
ROUTE_COUNTS = {
    "toy_train": ((43, 3), (57, 44), (36, 4), (49, 9), (31, 2), (45, 6)),
    "books": ((38, 2), (52, 4), (47, 3), (41, 2), (34, 1), (46, 4)),
    "plush": ((39, 3), (53, 5), (44, 4), (32, 1), (48, 2), (37, 3)),
}
OUTPUT = Path(__file__).resolve().parent
FIELDS = [
    "delivery_id", "country", "gift_category", "carrier", "promised_at",
    "delivered_at", "delay_minutes",
]


def source_rows():
    """Return 772 varied flat records; positive signed delay means late."""
    rng = random.Random(SEED)
    rows = []
    start = datetime(2025, 12, 25, tzinfo=timezone.utc)
    for category in ("toy_train", "books", "plush"):
        for country_index, country in enumerate(("France", "Germany", "Spain")):
            for carrier_index, carrier in enumerate(("Reindeer Express", "Polar Parcel")):
                total, late_count = ROUTE_COUNTS[category][country_index * 2 + carrier_index]
                late_flags = [True] * late_count + [False] * (total - late_count)
                rng.shuffle(late_flags)
                for is_late in late_flags:
                    number = len(rows) + 1
                    promised = start + timedelta(minutes=number)
                    delay = rng.randint(30, 180) if is_late else rng.randint(-30, 0)
                    delivered = promised + timedelta(minutes=delay)
                    rows.append({
                        "delivery_id": f"delivery-{number:04d}",
                        "country": country,
                        "gift_category": category,
                        "carrier": carrier,
                        "promised_at": promised.isoformat().replace("+00:00", "Z"),
                        "delivered_at": delivered.isoformat().replace("+00:00", "Z"),
                        "delay_minutes": delay,
                    })
    return rows


def aggregate(rows, keys):
    """Compute expected rates directly from source records, without Elasticsearch."""
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    result = []
    for values, members in groups.items():
        total = len(members)
        late = sum(row["delay_minutes"] > 0 for row in members)
        result.append(dict(zip(keys, values), total=total, late=late,
                           late_rate=100.0 * late / total))
    return sorted(result, key=lambda row: (-row["late_rate"], *(row[k] for k in keys)))


def main():
    rows = source_rows()
    schema = pa.schema([
        (field, pa.int64() if field == "delay_minutes" else pa.string())
        for field in FIELDS
    ])
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, OUTPUT / "deliveries.parquet", version="1.0", compression="snappy")
    expected = {
        "01-inspect": rows[:5],
        "02-categories": aggregate(rows, ("gift_category",)),
        "03-investigate": aggregate(
            [row for row in rows if row["gift_category"] == "toy_train"],
            ("carrier", "country"),
        ),
    }
    (OUTPUT / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    print(f"Generated {len(rows)} deliveries with seed {SEED}; "
          f"{sum(row['delay_minutes'] > 0 for row in rows)} late deliveries.")


if __name__ == "__main__":
    main()
