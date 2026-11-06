# Past archives and future plans in Kibana

The dashboard compares two different sources of synthetic data:

- **2025 history:** 360 delivery records in the external `santa_deliveries_2025` dataset, read from Parquet in MinIO through Data Federation.
- **2026 plan:** 18 route-plan documents in the Elasticsearch lookup index `santa_delivery_plan_2026`. This is new synthetic planning data, not an indexed copy of the archive.

Setup creates or verifies the dashboard. Open the URL printed by `./demo.sh setup`, defaulting to [Santa's Archives: Past Delays, Future Plans](http://localhost:5601/app/dashboards#/view/santa-esql-past-and-plan). After a successful default/setup command in an interactive terminal, the script displays the configured username and password from private `.env` or environment overrides, then opens the dashboard in the default browser. Use `--no-open` to prevent browser opening. Noninteractive execution prints the URL without credentials and does not launch a browser.

## Panels and query families

The committed [dashboard definition](../dashboards/santa-archives.json) contains six native Kibana panels:

1. An image banner uses the unchanged [Santa and Elky illustration](../assets/santa-elky-christmas-past.png), stored in Kibana Files.
2. A Markdown introduction identifies the two sources and the late-delivery rule.
3. **[Elasticsearch] 2026 planned deliveries:** a bar chart querying only the indexed plan.
4. **[S3] 2025 late-delivery rate (%):** a bar chart querying only the external archive.
5. **[S3 + Elasticsearch] Toy-train exposure in 2026:** a table produced by one ES|QL query that joins the two sources.
6. A Markdown interpretation states the calculation, experimental boundary, and illustrative nature of the result.

The dashboard is a native saved Kibana dashboard. It does not embed an independently built web application or require another frontend dependency. The queries cover the complete fixed synthetic datasets; no date filter is included in them.

## Indexed plan

[data/plan.py](../data/plan.py) generates [delivery-plan.json](../data/delivery-plan.json) and [plan-expected.json](../data/plan-expected.json) deterministically. It creates one document for each category/country/carrier combination, with stable IDs. Each route plans 100 deliveries, except toy trains / France / Polar Parcel, which plans 240. All routes have `target_late_rate: 10.0`, expressed as a percentage.

The index uses `index.mode: lookup`, strict mappings, keyword join keys, an integer delivery count, and a numeric target rate. The Elasticsearch-only query is:

```esql
FROM santa_delivery_plan_2026
| STATS planned_deliveries = SUM(planned_deliveries) BY gift_category
| SORT planned_deliveries DESC, gift_category ASC
| LIMIT 10
```

Expected category volumes are **740 toy trains**, **600 books**, and **600 plush toys**, totaling **1,940 planned deliveries**. There are 18 documents, not 1,940 individual delivery records.

## The mixed-source query

The archive is the left side of a genuine multi-key `LOOKUP JOIN`; the indexed plan is the right side:

```esql
FROM santa_deliveries_2025
| WHERE gift_category == "toy_train"
| STATS historical_total = COUNT(*), historical_late = COUNT(*) WHERE delay_minutes > 0 BY gift_category, carrier, country
| LOOKUP JOIN santa_delivery_plan_2026 ON gift_category, carrier, country
| EVAL historical_late_rate = 100.0 * historical_late / historical_total, illustrative_late_deliveries = 1.0 * planned_deliveries * historical_late / historical_total
| KEEP carrier, country, historical_total, historical_late, historical_late_rate, planned_deliveries, target_late_rate, illustrative_late_deliveries
| SORT historical_late_rate DESC, carrier ASC, country ASC
| LIMIT 10
```

For Polar Parcel in France, the result combines **16 late deliveries out of 20 in 2025** with **240 planned deliveries in 2026**. Applying the historical rate without change gives `240 × 16 / 20 = 192` illustrative late deliveries. The other five toy-train routes each combine a 10% historical rate with 100 planned deliveries, giving 10 illustrative late deliveries. Each route also shows the separate 10% planning target.

These figures are a synthetic unchanged-rate scenario. They do not predict 2026 performance or imply that a carrier caused real delays. They demonstrate that one query can combine an external archive with current indexed data.

`./demo.sh run` validates this joined result against expectations computed directly from Python historical records and plan documents, independently of Elasticsearch. It also validates the three original archive queries and the indexed volume query.

## Dashboard API and safe reuse

[scripts/dashboard.py](../scripts/dashboard.py) uses Kibana's Dashboards API:

```http
GET /api/dashboards/santa-esql-past-and-plan
PUT /api/dashboards/santa-esql-past-and-plan
```

The [dashboard template](../dashboards/santa-archives.json) becomes the PUT body after setup resolves `__SANTA_HEADER_IMAGE_FILE_ID__` to the uploaded Kibana file ID. No machine-specific file ID is committed. The orchestrator first checks the stable dashboard ID. It creates a missing dashboard, retrieves it, and verifies the requested content while allowing only the exact API defaults recorded in [api-defaults.json](../dashboards/api-defaults.json), plus generated panel IDs. Added queries, filters, pinned controls, or changed sampling are rejected. An existing dashboard must carry the demo ownership marker and match the committed definition. A foreign or changed dashboard is not overwritten. Setup can upgrade the exact previous five-panel layout by adding the banner and shifting the existing panels downward; it verifies the full previous content first. The setup does not use the Saved Objects API.

`./demo.sh setup --skip-dashboard` checks an existing compatible dashboard without creating one. `--skip-indexed-data` similarly requires the plan index, its strict mapping and ownership marker, and every expected document. The original four skip options remain independent of these two additions. `./demo.sh status` checks both resources.

`down` preserves the index and dashboard through the owned persistent volumes. `reset` deletes them only by deleting this demo's owned Elasticsearch/Kibana volumes. Cleanup never calls index or dashboard deletion APIs on external services.

## Validation boundary

On the recorded ARM64 SNAPSHOT, the indexed-only query and mixed-source join returned the independent expected results. Dashboard API creation, retrieval, and compatible reuse also passed. A browser rendering check also passed: both bar charts showed the expected data, and the mixed table showed six rows including the 192 scenario value, without page errors or HTTP responses of 400 or above. The final fresh setup/lifecycle matrix is recorded in [validation.md](validation.md).

For an earlier checkout with a different configuration fingerprint, restore its configuration or explicitly reset owned demo data before setting up this extension. The disk-watermark configuration changed to reserve local free space while keeping allocation safeguards enabled. This demo is not a production index-upgrade or dashboard-migration procedure.

## Header image

Setup uploads the original `assets/santa-elky-christmas-past.png` (2172 × 724)
without resizing or re-encoding it. The native image panel displays it with
`object_fit: contain` above the introduction. It needs no external image URL or
additional image server. Matching files are discovered using demo metadata and
SHA-256, and downloaded bytes are verified before reuse. Repeated setup preserves
the same file ID. `--skip-dashboard` requires both the dashboard and its image.

The Files service uses **internal Kibana APIs** in the tested snapshot, including
`POST /api/files/files/defaultImage`, binary `PUT .../{id}/blob`, metadata/list,
and download routes. They require authentication and an
`x-elastic-internal-origin` header. No Kibana security policy is changed. These
routes are version-specific and must be retested when changing Kibana versions.
The public Dashboards API still manages the dashboard itself. The current
`defaultImage` upload limit is 10 MiB.

Image files are not included in a normal dashboard export. Use `./demo.sh setup`
in the destination environment to upload the committed asset and resolve its
local file ID. Cleanup never calls Files deletion APIs against external Kibana.
