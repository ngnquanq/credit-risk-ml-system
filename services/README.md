# Services

Every folder here is something that gets deployed. A service owns its code, its image, the manifests that deploy it, and its tests' fixtures. Services talk to each other through **contracts**, never by importing each other's code.

| Service | What it does | Deploys as | Reads / writes |
|---|---|---|---|
| [`loan-api`](loan-api/README.md) | Accepts applications, decides who may do what, records decisions and the audit trail | API image; consumers and decision-recorder image | PostgreSQL, Kafka, MinIO |
| [`stream-features`](stream-features/README.md) | Turns change events into feature rows (Flink) and creates topics and connectors | Flink cluster and two jobs | Kafka |
| [`feature-store`](feature-store/README.md) | Defines features in Feast and writes them to the online store | Materialiser, Redis, registry job | Kafka, Redis |
| [`scoring`](scoring/README.md) | Scores one application and returns a decision band with reasons | BentoML on KServe | Redis, model bundle |
| [`model-lifecycle`](model-lifecycle/README.md) | Trains, registers, promotes, builds and deploys models | KFP pipeline, two watchers, a build Job | MLflow, MinIO |

Shared by more than one service, and therefore not owned by any of them:

- [`../contracts/`](../contracts): OpenAPI for the Loan API, `reason_map.json`, and `feature_catalog/` (feature definitions, model feature sets, reason texts).
- [`../platform/`](../platform): infrastructure the services run on (Kafka, ClickHouse, Prometheus, operators). It will move to `infra/`.

## Where does new code go?

1. It belongs to exactly one service: put it there, with its tests and its manifest.
2. Two services need it: do not import across services. Put the shared definition in `contracts/` (data, schema or a small loader), or copy the few lines.
3. It is infrastructure that several services run on: `platform/`.
4. An experiment or notebook: `notebook/`. Production code never imports from it.

The rule in 2 is checked in CI by `lint-imports` (contracts in `pyproject.toml`). When it fails, the message names the two modules. The fix is to move the shared piece to `contracts/`, not to silence the check.

## Running things

The commands live in the root [`Makefile`](../Makefile) today (`make help`). Each service README lists the ones that matter to it.

## Configuration

Three kinds, kept apart:

| Kind | Where it lives | Example |
|---|---|---|
| Where services find each other (public) | `platform/config/endpoints/endpoints.env`, turned into the `shared-endpoints` ConfigMap by a Kustomize component | `KAFKA_BOOTSTRAP_SERVERS` |
| Differs per environment | an overlay in `platform/environments/<env>` | replicas, hosts, image digests |
| Secret | a Kubernetes Secret created outside git (`make k8s-secrets`), later an external secret store | passwords, keys |

To use the shared addresses, add the component to the service's `deploy/kustomization.yaml` (see `stream-features`), read them with `envFrom` or `valueFrom.configMapKeyRef`, and apply with `kubectl apply -k`. A unit test fails when a manifest writes the Kafka address out again; manifests not converted yet are listed in `tests/unit/infra/test_endpoints_single_source.py`.
