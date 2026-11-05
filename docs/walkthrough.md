# Live demonstration walkthrough

Prepare with `./demo.sh setup`. Open Kibana Dev Tools and copy requests from [dev-tools.http](../queries/dev-tools.http). Keep credentials and `.env` out of the presentation. Run `./demo.sh run` beforehand to validate the exact build and archive.

1. **Introduce the archive.** “Santa is planning the next delivery run. The Ghost of Christmas Past has brought last year's archive: a Parquet file in an S3-compatible bucket. We will ask Elasticsearch questions about that file through ES|QL Data Federation.” Show the external dataset definition with `GET /_query/dataset/santa_deliveries_2025`. Point out its `s3://` resource and data-source reference.

2. **Inspect the records.** Execute the first query. “These are synthetic Christmas 2025 deliveries. A positive `delay_minutes` means late. We have 360 deliveries, with no customer names or addresses.” Point out that `FROM` names an external dataset and that no archive index was created.

3. **Find the category.** Execute the category-rate query. “Counts matter: each category has 120 deliveries. Toy trains have 26 late deliveries, about 21.67%; books and plush toys have 12 each, or 10%. Toy trains deserve a closer look.”

4. **Find the operational pattern.** Execute the carrier/country query. “Polar Parcel in France has 16 late toy-train deliveries out of 20: 80%. Every other toy-train group is at 10%. Santa now knows which part of the delivery operation to investigate.” Avoid implying this synthetic correlation proves a real-world cause.

5. **Close with the boundary.** “The results came from the Parquet archive through Data Federation, and the command-line replay checks them against independently generated expectations. Data Federation is experimental; Elastic officially documents Amazon S3 support. This MinIO setup is a compatibility experiment with the builds recorded in this repository.”

Replay the complete check with `./demo.sh run`. Stop containers with `./demo.sh down`; the uploaded object and Elastic state remain available for a later restart.
