# Santa's S3 Archives with ES|QL

A runnable companion demo for **“The Ghost of Christmas Past: Querying Santa’s S3 Archives with ES|QL”**.

Santa is preparing the 2026 delivery run. The Ghost of Christmas Past asks him to investigate Christmas 2025 delays. The archive is a small Parquet object in local MinIO. Elasticsearch queries that object through **ES|QL Data Federation**, without ingesting the historical records into an index. A separate synthetic 2026 plan lives in Elasticsearch. A native Kibana dashboard shows queries against each source, plus a real ES|QL join between them.

> **Validated locally on ARM64.** The complete default command passed from empty owned persistent state. All five queries matched independent expectations, including the real S3-to-Elasticsearch `LOOKUP JOIN`. The native dashboard rendered both charts and the joined table correctly. Repeated setup, all skip steps, missing/incompatible resources, and down/restart passed; see the [validation record](docs/validation.md).
>
> **Experimental compatibility:** Elastic documents Amazon S3 support and explicitly excludes other S3-compatible services from validated support. MinIO is an intentional local compatibility experiment. A successful run demonstrates compatibility with the recorded builds only; it does not establish official MinIO support. The federation feature itself is experimental.

## Prerequisites

- Docker with the Compose plugin, installed and already running. The script never launches or reconfigures Docker Desktop.
- Python 3.10–3.14 with `venv` and `pip`. Dependencies are pinned in [requirements.txt](requirements.txt), including PyArrow `23.0.1` and Boto3 `1.40.70`.
- Recommended starting allocation: at least 8 GiB RAM for Docker, several CPU cores, and 12 GiB free disk space for images, Go build cache, and persistent volumes. The validation host allocated approximately 16 GiB to Docker.
- Network access to the Elastic image registry, Docker Hub for the Go builder, GitHub, the Go module services, and PyPI on the first run.
- Available localhost ports `9200`, `5601`, `9000`, and `9001`, or customized host ports before first setup.

The selected images are Elasticsearch and Kibana **`9.6.0-SNAPSHOT`**. ARM64 and AMD64 manifests exist; execution was validated on Apple Silicon / Linux ARM64. SNAPSHOT tags are mutable: use the exact digests in the validation record when comparing results.

MinIO is built locally from the official **`RELEASE.2025-10-15T17-29-55Z`** source, pinned to a commit and archive checksum. Pull attempts for an older MinIO tag from Docker Hub and Quay, and `quay.io/minio/minio:latest`, returned denied/unauthorized responses on the validation host. See [source-build provenance](config/minio-build.md). This keeps MinIO as the server and requires no MinIO source changes.

## Quick start

```sh
git clone https://github.com/dadoonet/2026-12-advent-esql-data-fed.git
cd 2026-12-advent-esql-data-fed
./demo.sh
```

The default command performs `setup`, then `run`. It:

1. Creates a local `.venv` and installs pinned dependencies.
2. Generates private local credentials in `.env` if the file does not exist.
3. Builds and starts MinIO, prepares the Elasticsearch keystore, and starts Elasticsearch and Kibana.
4. Regenerates the deterministic Parquet file and uploads it to `santa-archives/christmas-2025.parquet`.
5. Registers the `santa_minio` data source and `santa_deliveries_2025` external dataset.
6. Generates and indexes 18 synthetic 2026 route plans in the lookup index `santa_delivery_plan_2026`.
7. Creates or verifies the native Kibana dashboard, using the Dashboards API.
8. Runs five queries and compares every result with expectations derived independently from the generators’ source records.

Open the [Santa dashboard](http://localhost:5601/app/dashboards#/view/santa-esql-past-and-plan) and sign in as `elastic` using `ES_PASSWORD` from your private `.env`. The setup output prints the URL for custom endpoints. Keep that file private. No credentials are printed by the orchestrator. [queries/dev-tools.http](queries/dev-tools.http) contains copy-paste requests for Kibana Dev Tools. [docs/walkthrough.md](docs/walkthrough.md) provides a short live-demo script. [Dashboard details](docs/dashboard.md) explain the indexed, external, and joined panels.

The supplied Santa/Elky illustration appears as a native image banner. Setup uploads and verifies the original PNG in Kibana and resolves its local file ID automatically. See [header-image provisioning](docs/dashboard.md#header-image) for the snapshot-specific internal Files API dependency.

## Commands and incremental execution

`./demo.sh` is the only required command interface:

- `setup`: prepare services, upload the archive, register federation resources, index the 2026 plan, and create or verify the dashboard; do not run the demonstration queries.
- `run`: execute and validate the queries against an existing setup.
- `status`: check service readiness, the object contents, federation definitions, the indexed plan, and the dashboard.
- `down`: remove this demo's containers and network, preserving persistent data.
- `reset`: remove this demo's containers, network, persistent volumes, and `.local` results. Requires typing `reset` interactively, or `--yes` for unattended use.
- `help`: show options and examples.

The default command and `setup` accept these options:

- `--skip-stack-start`: reuse the configured Elasticsearch and Kibana endpoints; both must be ready.
- `--skip-s3-start`: reuse the configured S3 endpoint; authentication must succeed.
- `--skip-data-upload`: skip generation and upload; the existing object's SHA-256 must match the committed Parquet file.
- `--skip-registration`: reuse compatible data-source and dataset definitions; both must already exist.
- `--skip-indexed-data`: reuse the 2026 lookup index; its mapping, ownership, and all 18 documents must match.
- `--skip-dashboard`: reuse the dashboard; its managed definition must match.

Skipped prerequisites are checked. Setup refuses to overwrite an incompatible existing object, federation definition, lookup index, or dashboard. Repeated setup reuses healthy services and compatible resources. Existing data-source credentials are redacted by Elasticsearch, so their values cannot be verified by GET; executing the queries verifies access.

```sh
# Start and validate everything.
./demo.sh

# Reuse Elasticsearch and Kibana; prepare MinIO and federation resources.
./demo.sh --skip-stack-start

# Reuse all services and the existing uploaded object.
./demo.sh --skip-stack-start --skip-s3-start --skip-data-upload

# Reuse every prepared resource and validate the five queries.
./demo.sh --skip-stack-start --skip-s3-start --skip-data-upload --skip-registration --skip-indexed-data --skip-dashboard

# Prepare once, replay independently.
./demo.sh setup
./demo.sh run
./demo.sh status

# Stop, then restart while keeping the object and federation definitions.
./demo.sh down
./demo.sh setup --skip-data-upload --skip-registration --skip-indexed-data --skip-dashboard
./demo.sh run

# Delete only this demo's owned persistent data.
./demo.sh reset --yes
```

## Configuration and ownership

For defaults, let `./demo.sh` generate `.env`. To customize before first setup, copy [.env.example](.env.example) to `.env` and replace every `CHANGE_ME` value with a strong local secret. Protect a manually created `.env` with `chmod 600 .env`. Use unquoted `KEY=value` entries; shell expressions are not evaluated. Environment variables override `.env`.

- `ES_VERSION` and `KIBANA_VERSION` select image tags independently; use matching versions.
- `ES_PORT`, `KIBANA_PORT`, `S3_PORT`, and `S3_CONSOLE_PORT` select host ports. Default host endpoints are derived from those ports.
- `ES_URL`, `KIBANA_URL`, and `S3_URL` override the host-facing endpoints, including external services.
- `S3_ES_ENDPOINT` is the S3 URL **seen by Elasticsearch**, defaulting to `http://minio:9000`. Host `localhost` refers to the Elasticsearch container itself and cannot reach MinIO.
- `S3_REGION` defaults to `us-east-1`; it is registered on the dataset.
- `READY_TIMEOUT` bounds each readiness check in seconds, default `240`.
- `ES_JAVA_OPTS` can override the default `-Xms1g -Xmx1g` heap settings.

Elasticsearch security stays enabled. Local HTTP is used on localhost and the private Compose network. The node permits only `minio:9000` as an additional federation endpoint host, and the S3 source uses explicit path-style addressing. Changing the container-visible endpoint also requires an appropriately narrow `esql.external.allowed_endpoint_hosts` setting on Elasticsearch.

Data Federation requires an active Enterprise or Trial license. Fresh owned clusters start with a trial; setup attempts `POST /_license/start_trial?acknowledge=true` when the configured cluster lacks an active qualifying license. An already exhausted trial cannot be restarted this way.

S3 credentials are encrypted in cluster state. Setup provisions `cluster.state.encryption.active_password_id` and `cluster.state.encryption.password.santa-demo` in the Elasticsearch keystore and reloads secure settings. The `es-config` volume and `CLUSTER_ENCRYPTION_PASSWORD` must be preserved together with `es-data`. An externally managed Elasticsearch cluster must already have federation enabled, endpoint authorization, cluster-state encryption, and suitable administrator credentials. Skip options do not configure these node prerequisites for it.

Compose uses project `santa-esql-advent-2026`, a private network, and ownership labels tied to this directory. Cleanup refuses resources with conflicting ownership. `down` and `reset` never delete S3 objects, federation definitions, indexes, or dashboards from external services selected through skip options. Setup can create these resources on configured external services; cleanup never calls their deletion APIs.

`reset` deletes the owned `es-data`, `es-config`, `kibana-data`, and `minio-data` volumes, plus `.local`. It retains `.env`, `.venv`, images/build cache, and committed dataset files. It therefore deletes the local trial cluster, federation definitions, indexed 2026 plan, dashboard, and uploaded archive. It never runs a global Docker prune. Do not move the directory while its containers or volumes exist; ownership is tied to its path.

A stored configuration fingerprint prevents silently changing versions, ports, credentials, or mounted configuration while reusing persistent data. Restore the original configuration, or deliberately reset owned data before applying the new configuration.

## Historical dataset and three archive queries

[data/generate.py](data/generate.py) uses fixed seed `20251225` and writes 360 flat synthetic records: 3 gift categories × 3 countries × 2 carriers × 20 deliveries. No personal data is included. [data/deliveries.parquet](data/deliveries.parquet) is small enough to commit.

Fields are `delivery_id`, `country`, `gift_category`, `carrier`, `promised_at`, `delivered_at`, and `delay_minutes`. Timestamps are simple UTC ISO-8601 strings. `delay_minutes` is the signed integer number of minutes from promised to actual delivery: negative means early, zero means on time, and **strictly positive means late**.

Inspect five records:

```esql
FROM santa_deliveries_2025
| KEEP delivery_id, country, gift_category, carrier, promised_at, delivered_at, delay_minutes
| SORT delivery_id ASC
| LIMIT 5
```

Rank categories by late-delivery rate, including counts:

```esql
FROM santa_deliveries_2025
| STATS total = COUNT(*), late = COUNT(*) WHERE delay_minutes > 0 BY gift_category
| EVAL late_rate = 100.0 * late / total
| SORT late_rate DESC, gift_category ASC
| LIMIT 10
```

Expected: `toy_train` has 26 late deliveries out of 120, approximately **21.67%**. `books` and `plush` each have 12 out of 120, **10%**.

Investigate toy trains by carrier and country:

```esql
FROM santa_deliveries_2025
| WHERE gift_category == "toy_train"
| STATS total = COUNT(*), late = COUNT(*) WHERE delay_minutes > 0 BY carrier, country
| EVAL late_rate = 100.0 * late / total
| SORT late_rate DESC, carrier ASC, country ASC
| LIMIT 10
```

Expected: **Polar Parcel / France** has 16 late deliveries out of 20, **80%**. Each other toy-train carrier/country group has 2 out of 20, **10%**. There are 50 late deliveries overall.

The generator computes [data/expected.json](data/expected.json) directly from its Python records, independently of Elasticsearch. The validator checks row order, columns, counts, values, and numeric rates with relative tolerance `1e-8` and absolute tolerance `1e-6`; partial results or warnings fail validation. Successful responses are saved locally under `.local`. No indexed copy of the historical archive is created, and `run` checks for an index/alias/data-stream conflict with the external dataset name.

## Three query families in one dashboard

The original three queries above read only the 2025 archive. Two additional tested queries extend the story:

- **Elasticsearch only:** [04-planned-volumes.esql](queries/04-planned-volumes.esql) sums the 2026 plan: 740 toy-train deliveries, 600 books, and 600 plush toys, or 1,940 planned deliveries in total.
- **External S3 only:** the category-rate panel uses the archive query above; the Parquet records remain in MinIO.
- **S3 + Elasticsearch:** [05-archive-plan-join.esql](queries/05-archive-plan-join.esql) aggregates historical toy-train deliveries, then `LOOKUP JOIN`s the indexed plan on `gift_category`, `carrier`, and `country`.

The plan has one document per category/country/carrier combination: 100 deliveries per route, except 240 toy trains for Polar Parcel in France. Every route has a 10% target late rate. Applying the historical 80% rate to that route’s 240 planned deliveries gives **192 illustrative late deliveries**, compared with 10 on each other toy-train route. This is a deliberately unchanged-rate scenario, not a forecast.

[data/plan.py](data/plan.py) deterministically generates the plan and its independent expected results from the source records. The dashboard contains five native panels: two explanatory Markdown panels, one bar chart per source, and one mixed-source table. See [docs/dashboard.md](docs/dashboard.md) for the full join and API lifecycle.

## Troubleshooting

- **Docker Desktop requires organizational sign-in:** this occurred during validation. Reconnecting with the required organization restored container operations; no Docker policy was changed. Already running query replay continued to work.
- **Index creation times out or a shard stays unassigned:** the Docker filesystem reached 90.1% usage during validation (about 10 GB free, below the default high-watermark requirement of roughly 10.2 GB). The local node now uses explicit free-space watermarks: low `3gb`, high `2gb`, and flood stage `1gb`. Disk safeguards remain enabled. Free disk space if those reserves are reached; the script does not change host Docker settings.
- **Docker is unavailable:** start Docker yourself and retry. The script will not launch the application or alter its configuration.
- **MinIO pull denied:** this was observed for Docker Hub, Quay's older pinned tag, and Quay's default tag. The demo builds the pinned official source automatically; see [provenance](config/minio-build.md). First build needs network access and can take several minutes.
- **`encryption_service_unavailable_exception`:** the first registration attempt on the recorded SNAPSHOT returned HTTP 503 because cluster-state encryption was disabled. Setup now prepares the secure keystore settings. External clusters require the same prerequisite. Preserve the encryption password and keystore with the Elasticsearch data.
- **`No limit defined, adding default limit of [1000]`:** this warning was observed on the aggregate queries. Each query now has an explicit limit, and validation rejects warnings rather than silently accepting them.
- **Skipped prerequisite missing:** run `./demo.sh setup` without the skip option named by the error, or correct the configured endpoint/credentials. An existing object is checked by content, not just its filename.
- **Dashboard is missing or modified:** run setup without `--skip-dashboard` to create a missing dashboard. Existing foreign or changed definitions are not overwritten; restore the committed definition, or explicitly remove the demo-owned dashboard in Kibana before recreating it.
- **Incompatible object or registration:** setup refuses to overwrite it. Restore the expected resource, or reset this demo's owned services. Do not reset external infrastructure to repair a local experiment.
- **Configuration fingerprint changed:** restore the original `.env` and configuration, or explicitly reset owned data before changing it. Increasing `READY_TIMEOUT` alone does not change persistent configuration.
- **Readiness timeout:** inspect the sanitized final error, run `./demo.sh status`, and check the relevant container logs. Verify port availability, version settings, and Docker memory allocation.

See [compatibility investigation](docs/compatibility.md) and [validation record](docs/validation.md) for exact builds, observed issues, and untested paths.

## Moving to the final 9.6 release

When `9.6.0` images are available, reset only this demo's owned resources, set `ES_VERSION=9.6.0` and `KIBANA_VERSION=9.6.0` in private `.env`, and run `./demo.sh` again. This intentionally discards the local test cluster; it is not a production upgrade procedure.

Recheck image architectures and digests, federation flags, endpoint restrictions, cluster-state encryption requirements, license activation, registration APIs, dataset region placement, lookup-index mappings, multi-key join syntax, the Dashboards API and rendered panels, all five expected query results, skip paths, and down/restart behavior. A successful SNAPSHOT run is not validation of the release.

No license has been assigned to this repository. Choosing one remains an owner follow-up. MinIO's upstream license is documented separately in its source-build provenance.
