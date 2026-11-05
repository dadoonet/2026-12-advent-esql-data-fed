# Validation record

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

Not tested: AMD64 execution, final 9.6 release, other snapshot builds, a real
Kibana browser interaction (the API returned ready), TLS/custom CA endpoints,
AWS access, managed/federated identity, trial activation on an existing Basic
cluster, an exhausted trial, remote externally managed Elasticsearch, production
scale, and long-running operation. No AWS or paid resources were accessed.
