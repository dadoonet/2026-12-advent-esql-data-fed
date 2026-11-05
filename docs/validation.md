# Validation record

This record includes the original three-query archive baseline and the subsequent
five-query indexed-plan/dashboard extension. The final extension results appear below.

Test date: **2026-11-05**, Europe/Paris. Host: macOS ARM64 (Apple Silicon),
Docker engine Linux `aarch64`, approximately 16 GiB Docker memory.
Python `3.14.8`; Docker client `29.8.2`, server `29.9.2`; Compose `v5.6.1`.

## Tested builds

- Elasticsearch `docker.elastic.co/elasticsearch/elasticsearch:9.6.0-SNAPSHOT`
  - Registry index digest: `sha256:ea3161009a4045865e364283c6c4dfe58911af4dce4ad8e45f37f790993b4cd3`.
  - ARM64 manifest: `sha256:616793f81ac948b8783680e9e10b8de114ea3403f7e67dd1502d8ce07d6d1d79`.
  - Local image ID: `sha256:fac8a241c07b5cdbf7182085963b8159a3c3abfb101d52f7e26fa896a32bda75`.
  - Build: `ab1cb79d28530e112b9178ebc14942d869410c7f`; image created `2026-11-04T23:36:20Z`.
- Kibana `docker.elastic.co/kibana/kibana:9.6.0-SNAPSHOT`
  - Registry index digest: `sha256:bda1258ea1c799fb3a5dfc2932f0d3e8adca1dbe66da434aafd54410faedd0a4`.
  - ARM64 manifest: `sha256:ca0a3d97429fff2893cc29d110a2dda1a8bf34b4d1f335ef138857e55779373b`.
  - Local image ID: `sha256:1c3fdd964005bfb92cd76a849c1079d1cd9f1ad2610932e0d1a0b2ae1b35f94a`.
  - Build: `a95773df3536f3d052df32358d64a9b704811e45`; build number `115040`, snapshot `true`.
- Locally built MinIO `santa-esql-advent-minio:source`, Linux ARM64
  - Release `RELEASE.2025-10-15T17-29-55Z`, official source commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`.
  - Local image ID: `sha256:f3a3278b11554557dd6c7f829945a17c24002d3fcd9f6cee4a088d34dc42ae57`.
  - No registry digest: built locally. [Provenance](../config/minio-build.md) records the source checksum and builder digest.

Both Elastic registry manifests included Linux ARM64 and AMD64. Only ARM64
execution was tested. SNAPSHOT tags can move; the digests above identify this test.

## Executed successfully

The complete default `./demo.sh` command passed, followed by repeated setup,
query replay, status, each skip option individually, and all skip options together.
The final default pass started from an absent `.venv` and empty owned persistent
state after reset. It installed the pinned Python dependencies, started services,
uploaded the archive, registered both definitions, and validated all three queries.
The image cache was retained; the source-build step had been tested separately.

```sh
./demo.sh
./demo.sh setup
./demo.sh run
./demo.sh status
./demo.sh setup --skip-stack-start
./demo.sh setup --skip-s3-start
./demo.sh setup --skip-data-upload
./demo.sh setup --skip-registration
./demo.sh --skip-stack-start --skip-s3-start --skip-data-upload --skip-registration
./demo.sh down
./demo.sh setup --skip-data-upload --skip-registration
./demo.sh run
```

All query checks passed, without warnings or partial results:

- Five exact inspection rows matched source records.
- Categories: toy trains `26/120`, `21.666666666666668%`; books and plush each `12/120`, `10%`.
- Investigation: Polar Parcel / France `16/20`, `80%`; five other groups each `2/20`, `10%`.
- `GET /_resolve/index/santa_deliveries_2025` found no index, alias, or data stream.
  The named external dataset referenced the MinIO Parquet resource. No indexed
  copy was created.
- The remote object was verified by SHA-256 against the generated 9,021-byte file:
  `de6f9458d9149d68d997cd3c096682b06953c71685e93768df8b4a2d9e322cbc`. Skipped upload also preserved the local file's modification time.
- After down/restart, the object, registrations, and query results survived.
  The cluster-state encryption health indicator was `green`, state `ready`,
  `encryption_required: true`, with matching active/metadata password ID `santa-demo`.

Independent checks passed: deterministic byte-identical regeneration, Parquet
round-trip, all three validator positive/negative controls, shell syntax, Python
compilation, and Git whitespace checks. Generated local credentials were scanned
against intended publication files and Git history; no matches were found.

## Expected failures verified

With every skip option enabled, each host endpoint was independently pointed at
`http://localhost:19999` and `READY_TIMEOUT=3`. Missing S3, Elasticsearch, and
Kibana each failed with a bounded readiness error.

The uploaded object, dataset, and source were individually removed from the owned
fixture and then restored. Skipping the relevant preparation failed with a helpful
message. An incompatible dataset resource and incompatible object contents were
also rejected and remained unchanged until explicitly restored by the test.
`./demo.sh run` after `down` failed with a service-unavailable message.

The [command results](validation-results.json) record commands and expected-failure
assertions without credentials.

## Issues found and fixed

- Official MinIO image pulls failed from Docker Hub and Quay, including the
  suggested `quay.io/minio/minio:latest`. The pinned official source build and
  `--version` check succeeded; the running image provided the archive to Elasticsearch.
- Initial source registration returned HTTP 503 because cluster-state encryption
  was unavailable. Persistent secure keystore settings fixed the failure.
- Initial aggregate queries emitted the implicit-limit warning. Explicit limits
  removed it; every final query now passes the warning check.
- Review caught an absent-index 404 handling issue and adoption risk for exact-name,
  unlabelled Docker volumes. Both were corrected before publication.

## Cleanup and fresh bootstrap verified

Additional tests passed:

- `./demo.sh reset` without interactive confirmation refused deletion and left
  the same containers present; `./demo.sh reset --yes` removed all four owned
  volumes and the owned containers/network.
- A separate MinIO container and volume were prepared on port `19000`, then used
  as `S3_URL` during setup with stack/S3 startup and registration skipped. Its
  uploaded object, volume, and service survived both `down` and `reset`. This
  tests external cleanup isolation; it does not claim a second external-federation
  configuration was queried. The fixture was removed explicitly afterward.
- Unlabelled volumes and networks with exact reserved names were preserved.
  Both setup and reset refused them with an ownership error. Only the test
  removed those fixtures afterward.
- A nonexistent `DOCKER_HOST` produced the helpful Docker prerequisite error.
- Changing only `READY_TIMEOUT` did not trigger the persistent-config guard.
- After reset and moving aside the old virtual environment, plain `./demo.sh`
  bootstrapped successfully. Subsequent `run` and `status` also passed.

Docker Desktop temporarily rejected container operations with an organizational
sign-in requirement (`Membership in the [elastic] organization is required`).
The user reconnected; the entire final cleanup/bootstrap phase then completed.
No host Docker policy was changed. Existing query replay remained usable during
that interruption.

## Untested paths

Not tested: AMD64 execution, final 9.6 release, other snapshot builds, TLS/custom CA endpoints,
AWS access, managed/federated identity, trial activation on an existing Basic
cluster, an exhausted trial, remote externally managed Elasticsearch, production
scale, and long-running operation. No AWS or paid resources were accessed.

## Indexed plans and dashboard extension — 2026-11-05

The same Elastic image tags/digests and MinIO source image above were reused.
The extension was validated after `./demo.sh reset --yes`, starting with empty
owned Elasticsearch, Kibana, and MinIO volumes; images and the existing Python
virtual environment were retained. Plain `./demo.sh` successfully prepared both
sources and the dashboard, then validated all **five** queries.

Additional verified results:

- Exactly 18 new synthetic 2026 plan documents in lookup index
  `santa_delivery_plan_2026`; the 2025 archive remains external.
- Elasticsearch-only volume totals: toy trains 740, books 600, plush 600;
  total planned deliveries 1,940.
- A real three-key `LOOKUP JOIN` after aggregation of the external dataset
  returned six toy-train routes. Polar Parcel / France combined 16/20 historical
  late deliveries with 240 planned deliveries, producing 192 illustrative late
  deliveries at the unchanged historical rate. Other routes produced 10 each.
- The right-hand lookup target is an Elasticsearch index; the left-hand source
  is the external Parquet dataset. A dataset as the lookup target was not used.
- `PUT /api/dashboards/santa-esql-past-and-plan` created the native dashboard;
  `GET` and subsequent setup verified the same ID without duplicates. The
  implementation uses the Dashboards API, with `kbn-xsrf`, rather than raw
  Saved Objects APIs. A generated-ID POST path was not used.
- Chrome headless rendered both bar charts and the six-row mixed table.
  The screenshot was visually inspected. Page errors and HTTP responses >=400
  were both empty. Login credentials were loaded in memory; browser state and
  screenshots remain local and uncommitted.

Commands passed: default setup+run, repeated `setup`, `run`, `status`, individual
`--skip-indexed-data` and `--skip-dashboard`, all six skip options together,
`down`, and restart using all four resource-reuse skips. Missing index/dashboard,
foreign dashboard ownership, dashboard content drift, and changed plan documents
failed as expected and were preserved until explicitly restored by the test.
See [extension command outcomes](dashboard-validation.json).

Final targeted controls reject added dashboard queries, global filters, pinned
controls, changed sampling, timed-out lookup searches, and failed search shards.
The dashboard accepts only the exact recorded server defaults and generated
panel IDs. The complete default command passed again after these controls were
added. Existing syntax, query-copy, and publication-secret audits were repeated.

### Disk allocation issue diagnosed

The first lookup-index creation timed out with its primary shard unassigned.
`/_cluster/allocation/explain` reported `disk_threshold: NO`: the Docker volume
had about 10 GiB free (90.1% used), below the default high watermark's required
10.2 GiB. The owned demo now has explicit free-space reserves in
`config/elasticsearch.yml`: low 3 GiB, high 2 GiB, flood-stage 1 GiB. Disk
allocation/write safeguards remain enabled. No Docker Desktop policy or disk
size was changed and no unrelated images/volumes were pruned. Cold startup and
index creation succeeded with this configuration.

The earlier three-query results remain valid; the new index/dashboard are
additional resources. The original browser-test exclusion above is superseded
by this extension's actual rendering check. Still untested: other builds,
AMD64 execution, final 9.6 release, production scale, and external managed
Elasticsearch/TLS configurations. The 192 figure is an illustrative scenario,
not a forecast.

### Dependency alerts corrected before publishing the extension

GitHub reported six high-severity Dependabot alerts for the original
`urllib3==2.5.0` pin. Its advisory metadata identified `2.8.0` as the first
version fixing all six affected ranges. The pin is now `urllib3==2.8.0`.
Bootstrap checks every exact requirement, including transitive pins and the
nested PyArrow requirements, so an existing virtual environment is updated when
any pin changes. The complete default command passed with the corrected version.
A new temporary MinIO object was also uploaded, read back byte-for-byte, and
deleted successfully; the committed archive object was preserved.

## Header image — 2026-11-05

The supplied PNG `assets/santa-elky-christmas-past.png` was added unchanged as a
native image panel above the introduction. Original dimensions: 2172 × 724;
SHA-256: `1253d48bdc6d4ec08e65a905f28ec591bcad9a86cd5fab40741b7fe8fc88ed96`.

Authenticated Kibana Files API creation, binary upload, metadata retrieval, and
byte-for-byte download verification passed on the same recorded Kibana build.
The exact previous five-panel dashboard was upgraded to six panels after a full
compatibility check. Repeated verification reused the image file ID; setup with
all six skip flags and status both passed. Browser checks confirmed the image's
original natural dimensions, preserved aspect ratio, and the existing charts and
joined data, with no page or HTTP errors. The screenshot was visually inspected.

The internal Files API requires `x-elastic-internal-origin` in this snapshot;
the header is supplied only to Files requests. No Kibana configuration or security
policy was changed. Public Dashboard API requests still manage the dashboard.
The committed template contains a runtime file-ID placeholder; no environment's
actual file ID is committed. Image Files API compatibility must be retested for
other Kibana builds. A new full reset/down cycle was not repeated for this visual
change; the previous lifecycle results remain recorded above.
