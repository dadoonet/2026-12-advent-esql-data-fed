# Compatibility investigation

This document separates official requirements from observations of this local experiment. The current execution outcome belongs in [validation.md](validation.md).

## Official behavior and source verification

[Elastic's external data-source documentation](https://www.elastic.co/docs/reference/query-languages/esql/esql-data-federation-sources) names Amazon S3 as the supported storage type and explicitly states that other S3-compatible services have not been validated and are not supported. MinIO is therefore an experiment, regardless of whether these requests succeed locally.

The official [release notes](https://www.elastic.co/docs/release-notes/elasticsearch) describe Data Federation as experimental and provide the feature flags:

```yaml
# Elasticsearch node setting
esql.federation.enabled: true

# Kibana setting
xpack.dataFederation.enabled: true
```

The [data-source settings reference](https://www.elastic.co/docs/reference/query-languages/esql/esql-data-federation-data-source-settings) describes endpoint restrictions, authentication, and addressing style. The default endpoint policy accepts supported AWS HTTPS endpoints. An additional host must be authorized explicitly with the static node setting `esql.external.allowed_endpoint_hosts`. An authorized custom S3 endpoint may use HTTP. This demo permits exactly `minio:9000`, without a wildcard or unrelated security changes:

```yaml
esql.external.allowed_endpoint_hosts: ["minio:9000"]
```

The source uses `auth: static_credentials`, an access key and secret key, and `addressing_style: path`. This produces paths such as `/santa-archives/christmas-2025-v2.parquet` rather than requiring a bucket subdomain. `http://minio:9000` is reachable through Docker's service DNS on the shared Compose network. `http://localhost:9000` inside Elasticsearch would address its own container.

The [dataset settings reference](https://www.elastic.co/docs/reference/query-languages/esql/esql-data-federation-dataset-settings) places `region` on the dataset. The current 9.6 S3 source also confirms that a source-level region is retained for backward compatibility but ignored. This demo explicitly sets dataset region `us-east-1` to avoid discovery ambiguity with a custom endpoint.

Source investigation first used the 9.6 branch at `b33935e610836c778a70b5383de17e6c6462916d`. The observed Elasticsearch SNAPSHOT reports build **`ab1cb79d28530e112b9178ebc14942d869410c7f`**. Relevant source locations include:

- [S3 endpoint checks](https://github.com/elastic/elasticsearch/blob/b33935e610836c778a70b5383de17e6c6462916d/x-pack/plugin/esql-datasource-s3/src/main/java/org/elasticsearch/xpack/esql/datasource/s3/S3EndpointCheck.java): custom-host authorization and HTTP exception.
- [S3 plugin](https://github.com/elastic/elasticsearch/blob/b33935e610836c778a70b5383de17e6c6462916d/x-pack/plugin/esql-datasource-s3/src/main/java/org/elasticsearch/xpack/esql/datasource/s3/S3DataSourcePlugin.java): source configuration and dataset-region handling.
- [License checker](https://github.com/elastic/elasticsearch/blob/b33935e610836c778a70b5383de17e6c6462916d/x-pack/plugin/esql/src/main/java/org/elasticsearch/xpack/esql/session/EsqlLicenseChecker.java): Enterprise or active Trial requirement.
- [Exact-build cluster-state encryption documentation](https://github.com/elastic/elasticsearch/blob/ab1cb79d28530e112b9178ebc14942d869410c7f/docs/reference/elasticsearch/cluster-state-encryption-key.md): secure keystore settings and reloading.

## Registration and queries

Official API references: [create data source](https://www.elastic.co/docs/api/doc/elasticsearch/v9/operation/operation-esql-put-data-source), [create dataset](https://www.elastic.co/docs/api/doc/elasticsearch/v9/operation/operation-esql-put-dataset), and [query external datasets](https://www.elastic.co/docs/reference/query-languages/esql/esql-data-federation-querying).

The orchestrator sends the following shapes, substituting private credentials in memory:

```http
PUT /_query/data_source/santa_minio
{
  "type": "s3",
  "settings": {
    "auth": "static_credentials",
    "access_key": "<LOCAL_ACCESS_KEY>",
    "secret_key": "<LOCAL_SECRET_KEY>",
    "endpoint": "http://minio:9000",
    "addressing_style": "path"
  }
}

PUT /_query/dataset/santa_deliveries_2025
{
  "data_source": "santa_minio",
  "resource": "s3://santa-archives/christmas-2025-v2.parquet",
  "settings": {"region": "us-east-1"}
}
```

GET responses wrap definitions in `data_sources` and `datasets` arrays. Source secrets are redacted. Setup compares visible connection settings and the dataset definition; it refuses an incompatible definition. A narrowly guarded revision upgrade may change the dataset resource from the exact known previous archive to the v2 object, after verifying its digest and compatible settings. It preserves those settings, including `region` and an optional `schema_resolution: first_file_wins`. Queries use ordinary `FROM santa_deliveries_2025` through `POST /_query`.

## Cluster-state encryption discovered during execution

The first actual source-registration attempt failed with HTTP 503:

```text
cannot store secrets for data source [santa_minio]:
cluster state encryption is unavailable (disabled).
Configure cluster.state.encryption.active_password_id and the matching
cluster.state.encryption.password.<id> in the keystore.
```

Custom security/HTTP configuration bypasses the automatic setup that otherwise provisions a cluster-state encryption password. Both the active password ID and its matching password are **secure keystore settings**, not `elasticsearch.yml` settings.

Setup now writes `cluster.state.encryption.active_password_id` with value `santa-demo` and `cluster.state.encryption.password.santa-demo` with a generated local password, using `elasticsearch-keystore add --stdin --force`. The password is passed on stdin and never logged. It persists in private `.env`; the keystore persists in `es-config`. Setup reloads secure settings with `POST /_nodes/reload_secure_settings`. The default requirement for encryption remains enabled. This prerequisite is separate from trial licensing.

## Query and dashboard revisions

The earlier revision successfully executed all five queries on the observed build: three external archive queries, one indexed-plan query, and a genuine multi-key `LOOKUP JOIN`. It also passed native dashboard API and browser checks. Those executed results are retained in [validation.md](validation.md). Initial aggregate queries returned `No limit defined, adding default limit of [1000]`; explicit `LIMIT 10` clauses avoid that warning.

The current varied-data revision uses 772 historical records, 102 late deliveries, and 18 indexed plan documents totaling 2,485 deliveries. Historical toy-train delays are 68 of 261 (about 26.05%). The join uses the keys `gift_category`, `carrier`, and `country` from the external `santa_deliveries_2025` dataset to `index.mode: lookup` index `santa_delivery_plan_2026_v2`. Polar Parcel / France combines 44 late records out of 57 with 290 planned deliveries and an 8% target, yielding about 223.9 illustrative late deliveries and a +69.19 percentage-point gap. The historical archive remains external.

The current dashboard template uses six native panels, including the existing image banner. It maps gift categories to red/orange/green and conditionally colors only the calculated `late_rate_gap` metric. Dynamic metric coloring applies thresholds to that metric's own value. Computing the difference in ES|QL avoids pretending the table can color a historical-rate cell using another column's route-specific target. Full-precision values determine threshold membership; one-decimal formatting affects display only. See [dashboard.md](dashboard.md) for the exact rules and boundary cases.

Setup preserves the previous S3 object and lookup index, uploads `christmas-2025-v2.parquet`, and creates `santa_delivery_plan_2026_v2`. The unchanged external dataset name is updated only for a verified known prior resource and compatible settings. Kibana's stable dashboard ID is similarly upgraded only if its complete content matches the committed previous six-panel fixture or the exact five-panel layout before the banner. Unknown resources and changed content are refused. No reset or old-data deletion is part of this normal revision upgrade.

Live query, API, guarded upgrade, and repeated-setup validation passed for this revision. Browser inspection verified the Santa category colors and all six target-gap cells, with two red, two orange, and two green. No page or HTTP errors were observed. The validation record distinguishes these checks from earlier cold-start/lifecycle results.

During index creation, the Docker filesystem reached about 90.1% usage: approximately 10 GB free, below the default high-watermark reserve of roughly 10.2 GB. The shard could not allocate and index creation timed out. The local node configuration now uses explicit free-space allocation thresholds of low `3gb`, high `2gb`, and flood stage `1gb`; disk safeguards remain enabled, and host Docker settings are unchanged. Earlier persistent configurations require an explicit owned-data reset because their recorded configuration fingerprint differs.

The complete default-command and lifecycle matrix is recorded separately in [validation.md](validation.md).

## Why Compose instead of start-local

The official [elastic/start-local repository](https://github.com/elastic/start-local) supports selecting an Elastic version, authenticated local HTTP services, localhost bindings, and a trial. Its generated Compose configuration does not directly expose this experiment's federation flags, custom endpoint authorization, persistent encryption-keystore provisioning, and independently managed MinIO lifecycle. Modifying generated files would add another configuration layer to maintain.

This repository uses one small Compose setup to make those settings explicit, with one project-scoped network and four persistent volumes. There is no second supported start-local path.

## MinIO distribution and limits

Observed pull attempts failed for:

```text
minio/minio:RELEASE.2025-04-22T22-12-26Z
  pull access denied / repository does not exist or may require login
quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z
  unauthorized: access to the requested resource is not authorized
quay.io/minio/minio:latest
  unauthorized: access to the requested resource is not authorized
```

These are observations from the validation host, not a claim that every registry or network must behave identically. The [official MinIO release instructions](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z) permit building from source. The demo therefore builds that official release without source patches; the [provenance record](../config/minio-build.md) includes immutable source and builder pins.

This experiment uses local static credentials, HTTP on a private Docker network, and explicit path addressing. It does not test AWS, paid cloud resources, TLS endpoints, managed identity, federated identity, production scale, or long-running operation. Official Amazon S3 support does not imply support for this configuration.
