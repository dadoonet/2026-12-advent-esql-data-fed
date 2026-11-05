# Live demonstration walkthrough

Prepare with `./demo.sh setup`. Open the dashboard URL printed by setup, and keep Kibana Dev Tools available with [dev-tools.http](../queries/dev-tools.http). Keep credentials and `.env` out of the presentation. Run `./demo.sh run` beforehand to validate all five queries against the exact build and data.

1. **Introduce past and future.** “Santa is planning the 2026 delivery run. His new plan is indexed in Elasticsearch. The Ghost of Christmas Past has brought last year's archive: a Parquet file in a local S3-compatible bucket. We will query both sources and then combine them.” Show the dashboard's introduction and the external dataset definition with `GET /_query/dataset/santa_deliveries_2025`. Point out the `s3://` resource.

2. **Inspect the archive.** Execute the first query. “These are 360 synthetic Christmas 2025 deliveries. A positive `delay_minutes` means late. No customer names or addresses are included.” Point out that `FROM santa_deliveries_2025` names an external dataset, and the historical records were never ingested into an archive index.

3. **Read the two source panels.** “The Elasticsearch panel shows the 2026 plan: 740 toy-train deliveries, 600 books, and 600 plush toys. The S3 panel reads the 2025 archive: toy trains had 26 late deliveries out of 120, about 21.67%; books and plush toys had 12 each, or 10%.” If useful, show the category-rate and planned-volume requests in Dev Tools.

4. **Find the route.** Execute the carrier/country archive query. “Polar Parcel in France had 16 late toy-train deliveries out of 20: 80%. Every other toy-train group was at 10%. Santa now knows which route to investigate.” Avoid implying this synthetic correlation proves a real-world cause.

5. **Join the sources.** Point to the dashboard's mixed-source table and execute the fifth request if explaining the query. “This is one ES|QL query. The external archive is aggregated first, then a three-key `LOOKUP JOIN` adds the indexed 2026 plan. The problematic route now plans 240 deliveries. At an unchanged 80% historical rate, that would be 192 illustrative late deliveries, against a 10% target. This is a scenario for discussion, not a forecast.”

6. **Close with the boundary.** “Only the new planning data was indexed. The 2025 records stayed in the Parquet archive, and command-line replay checks every query against independently generated expectations. Data Federation is experimental; Elastic officially documents Amazon S3 support. This MinIO setup is a compatibility experiment with the recorded builds.”

Replay all checks with `./demo.sh run`. Stop containers with `./demo.sh down`; the uploaded object, index, dashboard, and Elastic state remain available for a later restart.
