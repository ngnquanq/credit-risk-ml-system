# ADR-0015: One folder per deployable service; services share only contracts

## Status

Accepted. Supersedes the part of [ADR-0011](0011-monorepo-layout-for-portals-contracts-and-environments.md) that kept the feature catalog in `training/`.

## Date

2026-11-24

## Context

`application/` held ten folders and four Dockerfiles, `platform/` held manifests and also code that runs (watchers, the KFP pipeline, SQL, scripts), and `notebook/` held a file that production training needed. The goal is high cohesion inside a unit and low coupling between units, so that a new team member can work on one service without learning the rest.

Measured on this repository (not taken from a book):

- **Imports.** `scoring`, `flink`, `feast_repo` and `training` hardly import anything from the Loan API. The audit, authz, identity, decisions, domain, infrastructure, workflows and entrypoints folders import each other heavily, and they change together (`api` with `core` in 75% of the commits that touched either; with `infrastructure` 60%).
- **Change history** (38 recent commits). Code and the manifest that deploys it changed together most: `scoring` with `platform/ml/k8s` 71%, `notebook` with `platform/ml/k8s` 80%, `training` with `platform/ml` 43%. The `Makefile` changed with almost everything.
- **Duplication.** The schema SQL existed in three places, and the cluster copy had already drifted (shorter table comments). The feature catalog was reached through `training/` by the API and by scoring.
- **Cost of moving.** Each path was named in only 1 to 11 code or config files.

## Decision

1. **A service is the unit of cohesion.** `services/<name>/` holds the code, the image, the manifests that deploy it, and its README. The services are `loan-api`, `stream-features`, `feature-store`, `scoring` and `model-lifecycle`.
2. **Services share only contracts.** What more than one service needs lives in `contracts/` (OpenAPI, `reason_map.json`, `feature_catalog/`). No service imports another service. `lint-imports` enforces this in CI and in `make check`. One known exception, scoring's optional `core.tracing` import, is listed in `pyproject.toml` with its reason.
3. **Manifests of our own services sit next to their code.** `platform/` keeps what services run on (Kafka, ClickHouse, Prometheus, operators, ingress, identity). It is expected to become `infra/`.
4. **The schema has one source.** `services/loan-api/schema/` holds idempotent SQL that creates the operational database. The cluster ConfigMap is generated from it and a unit test fails on drift. Loading data is a different, one-off job and is not part of the schema.
5. **Import names do not change.** Packages such as `domain`, `scoring` and `training` keep their names; only their parent folders moved, and `pyproject.toml` lists the roots.

### What the evidence supports and what it does not

Supported by official documentation: several packages in one repository with a shared library and one lockfile (uv workspaces); a clear split between ML code and the resource definitions that deploy it (Databricks MLOps Stacks); a single repository suits tight integration and easy refactoring (Microsoft Learn). The uv documentation also warns that a workspace does not stop one package importing another's dependencies, which is why decision 2 needs a check.

Supported by the books in the project notebook: group what changes together inside one boundary and minimise coupling across boundaries (connascence, Richards and Ford); production code is not written in notebooks (Wilson); define a feature once (Wilson).

**Not supported by any source:** this folder tree. The notebook confirmed that none of its 52 sources prescribes one. Folding the decision recorder and consumers into `loan-api`, putting `feature_catalog` in `contracts/`, and the names `services/` and `model-lifecycle` are inferences from the measurements above.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Keep `application/` and `platform/` | No move | Mixed layers and deployables; code and its manifest far apart; shared catalog reached through `training/` |
| Split by technical layer (`api/`, `domain/`, `infra/`) | Familiar | One domain smeared over every layer; a change touches all of them |
| Split by ML lifecycle only (`data/`, `features/`, `training/`, `serving/`) | Matches MLOps diagrams | The Loan API, audit, authz and identity are not part of any ML lifecycle |
| Move only the four independent folders | Smallest change | Manifests and scripts stay split from the code that they deploy |
| Services, one folder each, shared contracts (chosen) | Matches deployables, imports and change history; boundary can be checked | The one-off cost of moving; some inferred choices |

## Consequences

### Positive

- A change to one service usually stays inside one folder, so reviews and CODEOWNERS follow the folders.
- The boundary is checked by a tool, not by memory.
- The schema cannot drift between the local stack and the cluster.

### Negative

- Every path moved. Open branches that touch moved files will conflict.
- `contracts/` now also holds Python (`feature_catalog`), so it is not only language-neutral files.
- The `Makefile` is still one file for all services.

### Risks

- The bento builder clones an application ref. Rebuilding from a commit made before this change needs the old `APP_SUBPATH` (`application/scoring`) and the old catalog path.
- The loan-api manifest `01-api-config.yaml` and `nginx.conf` were left in `platform/core` because of unfinished changes; they should follow `05-api.yaml` into `services/loan-api/deploy`.
- Neither `bootstrap/create_topics.py` nor `bootstrap/create-connectors.sh` is called by a make target. Delete them if they are not run by hand.
