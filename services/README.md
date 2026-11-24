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

Config and secrets are kept apart. Config that more than one service needs is defined once and reaches pods through ConfigMaps built by Kustomize components:

| What | Defined in | Read as |
|---|---|---|
| Addresses of other services | `platform/config/endpoints/endpoints.env` | `shared-endpoints` |
| Public host names (per environment) | `platform/config/public-hosts/hosts.env` | `public-hosts` |
| Kafka topic names | `contracts/topics/topics.env` | `shared-topics` |
| Image tags | `platform/config/images/kustomization.yaml` | applied by Kustomize |

To use one, add the component to the service's `deploy/kustomization.yaml` (see `stream-features`), read it with `envFrom`, `valueFrom.configMapKeyRef` or a `replacement`, and apply with `kubectl apply -k`. Unit tests in `tests/unit/infra` fail when a manifest writes one of these values out again. Secrets are Kubernetes Secrets created outside git.

Details, the table of every Secret, and the places that still pass a secret through a ConfigMap: [`docs/security/configuration-and-secrets.md`](../docs/security/configuration-and-secrets.md).
