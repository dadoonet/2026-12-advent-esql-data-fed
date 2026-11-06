# Past archives and future plans in Kibana

The dashboard compares two different sources of synthetic data:

- **2025 history:** 772 delivery records in the external `santa_deliveries_2025` dataset, read from Parquet in MinIO through Data Federation.
- **2026 plan:** 18 route-plan documents in the Elasticsearch lookup index `santa_delivery_plan_2026_v2`. This is new synthetic planning data, not an indexed copy of the archive.

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

[data/plan.py](../data/plan.py) generates [delivery-plan.json](../data/delivery-plan.json) and [plan-expected.json](../data/plan-expected.json) deterministically. It creates one document for each category/country/carrier combination, with stable IDs. The 18 route volumes are all different, ranging from 65 to 290 planned deliveries. Route-specific `target_late_rate` values range from 6% to 12%; they are expressed as percentages.

The index uses `index.mode: lookup`, strict mappings, keyword join keys, an integer delivery count, and a numeric target rate. The Elasticsearch-only query is:

```esql
FROM santa_delivery_plan_2026_v2
| STATS planned_deliveries = SUM(planned_deliveries) BY gift_category
| SORT planned_deliveries DESC, gift_category ASC
| LIMIT 10
```

Expected category volumes are **1,160 toy trains**, **765 plush toys**, and **560 books**, totaling **2,485 planned deliveries**. There are 18 route-plan documents rather than one document per planned delivery.

## The mixed-source query

The archive is the left side of a genuine multi-key `LOOKUP JOIN`; the indexed plan is the right side:

```esql
FROM santa_deliveries_2025
| WHERE gift_category == "toy_train"
| STATS historical_total = COUNT(*), historical_late = COUNT(*) WHERE delay_minutes > 0 BY gift_category, carrier, country
| LOOKUP JOIN santa_delivery_plan_2026_v2 ON gift_category, carrier, country
| EVAL historical_late_rate = 100.0 * historical_late / historical_total, illustrative_late_deliveries = 1.0 * planned_deliveries * historical_late / historical_total
| EVAL late_rate_gap = historical_late_rate - target_late_rate
| KEEP carrier, country, historical_total, historical_late, historical_late_rate, planned_deliveries, target_late_rate, late_rate_gap, illustrative_late_deliveries
| SORT historical_late_rate DESC, carrier ASC, country ASC
| LIMIT 10
```

For Polar Parcel in France, the result combines **44 late deliveries out of 57 in 2025** with **290 planned deliveries in 2026**. Applying the historical rate without change gives `290 × 44 / 57 ≈ 223.9` illustrative late deliveries. The route has an **8% target**, so its historical rate of approximately **77.19%** exceeds that target by **69.19 percentage points**. The other five routes have distinct counts, planned volumes, targets, and scenario values.

These figures are a synthetic unchanged-rate scenario. They do not predict 2026 performance or imply that a carrier caused real delays. They demonstrate that one query can combine an external archive with current indexed data.

`./demo.sh run` validates this joined result against expectations computed directly from Python historical records and plan documents, independently of Elasticsearch. It also validates the three original archive queries and the indexed volume query.

## Santa colors and gap-to-target semantics

Both bar charts use the same categorical mapping: `toy_train` is Santa red (`#D92D35`), `books` is orange (`#F59E0B`), and `plush` is green (`#2E7D50`). These chart colors identify categories; they do not classify performance against a target.

In the joined table, **only `late_rate_gap` is conditionally colored**. Its calculation is `historical_late_rate - target_late_rate`, expressed in percentage points (pp):

- Green: gap strictly below −2 pp.
- Orange: gap at least −2 pp and strictly below +5 pp.
- Red: gap at least +5 pp.

Thus the thresholds have no gaps or overlaps: exactly −2 pp is orange, and exactly +5 pp is red. Thresholds use the actual unrounded values; the table displays rates and gaps to one decimal place. Raw counts and rates remain neutral. Because route targets differ, coloring the historical rate alone would misrepresent the comparison. The tested table API applies a color rule to that metric's own value; the explicit gap column carries the cross-column calculation.

The six toy-train rows deliberately cover all three colors:

- Polar Parcel / France: 44 of 57 late, 290 planned, target 8%; gap about **+69.19 pp**, red; scenario about **223.9** late deliveries.
- Polar Parcel / Germany: 9 of 49 late, 225 planned, target 11%; gap about **+7.37 pp**, red; scenario about **41.3**.
- Polar Parcel / Spain: 6 of 45 late, 175 planned, target 12%; gap about **+1.33 pp**, orange; scenario about **23.3**.
- Reindeer Express / Germany: 4 of 36 late, 185 planned, target 12%; gap about **−0.89 pp**, orange; scenario about **20.6**.
- Reindeer Express / France: 3 of 43 late, 155 planned, target 10%; gap about **−3.02 pp**, green; scenario about **10.8**.
- Reindeer Express / Spain: 2 of 31 late, 130 planned, target 9%; gap about **−2.55 pp**, green; scenario about **8.4**.

The table uses short column labels and the final Markdown panel explains the distinction between category colors and gap colors.

## Dashboard API and safe reuse

[scripts/dashboard.py](../scripts/dashboard.py) uses Kibana's Dashboards API:

```http
GET /api/dashboards/santa-esql-past-and-plan
PUT /api/dashboards/santa-esql-past-and-plan
```

The [dashboard template](../dashboards/santa-archives.json) becomes the PUT body after setup resolves `__SANTA_HEADER_IMAGE_FILE_ID__` to the uploaded Kibana file ID. No machine-specific file ID is committed. The orchestrator first checks the stable dashboard ID. It creates a missing dashboard, retrieves it, and verifies the requested content while allowing only the exact API defaults recorded in [api-defaults.json](../dashboards/api-defaults.json), plus generated panel IDs. Added queries, filters, pinned controls, or changed sampling are rejected. An existing dashboard must carry the demo ownership marker and match the committed definition. A foreign or changed dashboard is not overwritten. Setup compares the full previous content against [the committed v1 fixture](../dashboards/previous/santa-archives-v1.json). It can upgrade that exact six-panel layout or its exact pre-banner five-panel form to the current template. It preserves the header-image file ID and refuses unknown content. The setup does not use the Saved Objects API.

`./demo.sh setup --skip-dashboard` checks an existing compatible dashboard without creating one. `--skip-indexed-data` similarly requires the plan index, its strict mapping and ownership marker, and every expected document. The original four skip options remain independent of these two additions. `./demo.sh status` checks both resources.

`down` preserves the index and dashboard through the owned persistent volumes. `reset` deletes them only by deleting this demo's owned Elasticsearch/Kibana volumes. Cleanup never calls index or dashboard deletion APIs on external services.

## Validation boundary

The varied-data revision passed all five live queries, the guarded upgrade, repeated setup, and full reuse. Browser inspection confirmed the category colors, aligned bars, one-decimal formats, and six mixed rows with exactly two cells of each gap color. There were no page errors or HTTP responses of 400 or above. Earlier cold-start/lifecycle checks and this revision’s validation scope are recorded in [validation.md](validation.md).

Normal upgrades preserve the old `christmas-2025.parquet` object and `santa_delivery_plan_2026` index. Setup uploads the v2 object, creates the v2 index, and changes the dataset pointer only after verifying the known old object digest and compatible settings. The resource name remains `santa_deliveries_2025`, with its existing compatible settings preserved. Unknown resources, modified dashboard content, or configuration drift are refused. Do not use the skip options for a resource that still needs this upgrade.

An unrelated node/Compose configuration-fingerprint change still requires restoring that configuration or explicitly resetting owned demo data. The varied-data and color upgrade itself does not require a reset. This is not a general production index-upgrade or dashboard-migration procedure.

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
