# Live demonstration walkthrough

Prepare with `./demo.sh setup`. Open the dashboard URL printed by setup, and keep Kibana Dev Tools available with [dev-tools.http](../queries/dev-tools.http). Keep credentials and `.env` out of the presentation. Run `./demo.sh run` beforehand to validate all five queries against the exact build and data.

1. **Introduce past and future.** “Santa is planning the 2026 delivery run. His new plan is indexed in Elasticsearch. The Ghost of Christmas Past has brought last year's archive: a Parquet file in a local S3-compatible bucket. We will query both sources and then combine them.” Show the Santa/Elky banner, the introduction, and `GET /_query/dataset/santa_deliveries_2025`. Point out the `s3://` resource.

2. **Inspect the archive.** Execute the first query. “These are 772 synthetic Christmas 2025 deliveries in 18 route groups with varied sizes. A positive `delay_minutes` means late. No customer names or addresses are included.” Point out that `FROM santa_deliveries_2025` names an external dataset, and the historical records were never ingested into an archive index.

3. **Read the two source panels.** “The Elasticsearch panel shows the 2026 plan: 1,160 toy trains, 765 plush toys, and 560 books. The S3 panel reads the 2025 archive: toy trains had 68 late deliveries out of 261, about 26.05%; plush toys had 18 out of 253, about 7.11%; and books had 16 out of 258, about 6.20%.” Show that both charts use Santa red for toy trains, orange for books, and green for plush toys. Those colors identify categories.

4. **Find the route.** Execute the carrier/country archive query. “Polar Parcel in France had 44 late toy-train deliveries out of 57: about 77.19%. The other routes have different counts and rates, and none comes close to that rate. Santa now knows which route to investigate.” Avoid implying this synthetic correlation proves a real-world cause.

5. **Join the sources.** Point to the mixed-source table and execute the fifth request if explaining the query. “This is one ES|QL query. The external archive is aggregated first, then a three-key `LOOKUP JOIN` adds the indexed 2026 plan. The problematic route plans 290 deliveries. At the unchanged historical rate, that would be about 223.9 illustrative late deliveries, against an 8% target. This is a scenario for discussion, not a forecast.”

6. **Explain the table colors.** “The targets vary by route. The colored column subtracts each route's target from its historical late rate, in percentage points. Green is below −2 points, orange runs from −2 to below +5, and red starts at +5. Here we have two routes in each color. The France/Polar Parcel gap is about +69.2 points.” Distinguish these gap colors from the categorical chart colors. Counts and raw rates remain neutral; displayed rounding does not change the thresholds.

7. **Close with the boundary.** “Only the new planning data was indexed. The 2025 records stayed in the Parquet archive, and command-line replay checks every query against independently generated expectations. Data Federation is experimental; Elastic officially documents Amazon S3 support. This MinIO setup is a compatibility experiment with the recorded builds.”

Replay all checks with `./demo.sh run`. Stop containers with `./demo.sh down`; the uploaded object, index, dashboard, and Elastic state remain available for a later restart.
