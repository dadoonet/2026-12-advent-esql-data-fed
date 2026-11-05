#!/usr/bin/env python3
"""Prepare a small owned lookup index without indexing the historical archive."""

import json
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
INDEX = "santa_delivery_plan_2026"
MARKER = {"santa_demo": "delivery-plan-v1"}
PROPERTIES = {
    "gift_category": {"type": "keyword"},
    "country": {"type": "keyword"},
    "carrier": {"type": "keyword"},
    "planned_deliveries": {"type": "long"},
    "target_late_rate": {"type": "double"},
}


def ensure(cfg, request, create=False):
    """Reuse compatible plans, optionally creating only absent owned resources."""
    documents = json.loads((ROOT / "data/delivery-plan.json").read_text())
    expected = {document["_id"]: document["_source"] for document in documents}
    if len(expected) != len(documents):
        raise RuntimeError("The committed delivery plan contains duplicate document IDs.")
    existing = request(cfg, "GET", f"/{INDEX}", missing_ok=True)
    if existing is None:
        if not create:
            raise RuntimeError(f"Required lookup index {INDEX} missing. Run ./demo.sh setup without --skip-indexed-data.")
        request(cfg, "PUT", f"/{INDEX}", {
            "settings": {"index.mode": "lookup", "number_of_replicas": 0},
            "mappings": {"dynamic": "strict", "_meta": MARKER, "properties": PROPERTIES},
        })
    else:
        if set(existing) != {INDEX}:
            raise RuntimeError(f"Refusing to reuse an alias or unexpected index for {INDEX}.")
        definition = existing[INDEX]
        settings = definition.get("settings", {}).get("index", {})
        mappings = definition.get("mappings", {})
        if (settings.get("mode") != "lookup" or str(settings.get("number_of_replicas")) != "0"
                or mappings.get("_meta") != MARKER
                or mappings.get("dynamic") != "strict"
                or mappings.get("properties") != PROPERTIES):
            raise RuntimeError(f"Existing lookup index {INDEX} has incompatible configuration or ownership; refusing to overwrite it.")
    response = request(cfg, "POST", f"/{INDEX}/_search", {
        "size": 10000, "track_total_hits": True, "query": {"match_all": {}},
    })
    hits = response["hits"]["hits"]
    total = response["hits"]["total"]
    if isinstance(total, dict):
        if total.get("relation") != "eq":
            raise RuntimeError("Cannot verify lookup index contents: search total is not exact.")
        total = total["value"]
    if len(hits) != total:
        raise RuntimeError("Cannot verify all lookup index documents; refusing to modify the index.")
    current = {hit["_id"]: hit["_source"] for hit in hits}
    if len(current) != len(hits):
        raise RuntimeError("Lookup search returned duplicate document IDs.")
    # Inspect every existing document before creating anything in a partial index.
    for identifier, source in current.items():
        if identifier not in expected or source != expected[identifier]:
            raise RuntimeError(f"Existing lookup index {INDEX} has incompatible documents; refusing to overwrite them.")
    missing = [identifier for identifier in expected if identifier not in current]
    if missing and not create:
        raise RuntimeError(f"Lookup index {INDEX} is missing {len(missing)} plan documents. Run ./demo.sh setup without --skip-indexed-data.")
    for identifier in missing:
        request(cfg, "PUT", f"/{INDEX}/_create/{quote(identifier, safe='')}?refresh=false", expected[identifier])
    if missing:
        request(cfg, "POST", f"/{INDEX}/_refresh")
    print(f"[indexed] Verified {len(expected)} compatible 2026 plans in lookup index {INDEX}", flush=True)
