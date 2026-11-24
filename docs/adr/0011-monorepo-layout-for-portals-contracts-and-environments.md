# ADR-0011: Monorepo layout for portals, contracts and environments

## Status

Accepted. The feature catalog location in decision 1 is superseded by [ADR-0015](0015-services-layout-high-cohesion-low-coupling.md).

## Date

2026-11-22

## Context

The release-readiness epics ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access)–[E16](../02-product/epics.md#e16-uat-and-release-readiness)) add code of new kinds to a repository that so far held Python services, Kubernetes manifests and docs:

- two Next.js (TypeScript) backends-for-frontend and shared TypeScript packages ([E12 Portals](../02-product/epics.md#e12-staff-and-applicant-portals));
- Keycloak realm configuration ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access));
- Python modules for authorization and audit ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access), [E13](../02-product/epics.md#e13-audit-trail));
- manifests for identity, portals and a UAT environment, plus release scripts ([E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover), [E16](../02-product/epics.md#e16-uat-and-release-readiness)).

One small team owns everything. We had to decide whether the portals and the deployment configuration get their own repositories, where per-environment configuration and secrets live, where shared contracts live, and how several deployables are released from one tree.

The sources below were cross-checked through the project's research notebook on 2026-11-22. The "Source" column says what a source states; the decision column is our inference.

| Question | Source | Decision |
|---|---|---|
| One repo or several | *Software Engineering at Google* ch. 16 (version control, one-version rule); DORA "Version control" (application code, tests and deployment configuration all in version control) | One repository |
| Config vs. code | Twelve-Factor App III (config in the environment) and V (build, release, run are separate stages) | Images built once per commit; config injected per environment |
| Per-environment config | Google SRE Workbook ch. 14–15 (separate abstract configuration from data; avoid copy-and-edit per environment) | Kustomize bases plus overlays per environment |
| Secrets | Kubernetes "Good practices for Secrets" (do not commit Secret manifests; prefer external stores or encryption at rest) | Secrets created at deploy time, never committed |
| Branching and ownership | DORA "Trunk-based development"; *Software Engineering at Google* ch. 9 and 16 (OWNERS files per directory) | Trunk-based on `master`; `CODEOWNERS` per path |
| Release of many deployables | *Software Engineering at Google* ch. 23 (build once, promote the same artifact) | Path-filtered builds; promote image digests through overlays |

## Decision

Keep everything in this repository with the layout below.

```text
application/            Python packages (one Docker build context per service)
  authz/                NEW  authorization policy (E11), pure Python, no I/O
  audit/                NEW  audit writer and sanitizer (E13)
  training/feature_catalog/   feature definitions and model sets (E2), owned by training
portals/                NEW  pnpm workspace (E12)
  apps/staff-portal/
  apps/applicant-portal/
  packages/api-client/  generated from contracts/openapi/loan-api.json
  packages/session/
  packages/ui/
contracts/              NEW  machine-readable interfaces that cross a language or deployable boundary
  openapi/loan-api.json       exported from FastAPI by `make contracts`; portals generate their client from it
platform/
  <plane>/k8s/          bases (unchanged location)
  core/k8s/identity/    NEW  Keycloak manifests and realm exports (no secrets)
  core/k8s/portals/     NEW
  environments/         NEW  Kustomize overlays: dev/, uat/ (image digests, replicas, hosts)
scripts/                release, UAT seeding and chaos drills
docs/                   unchanged chain: business → epics → architecture → handoff → release
```

Rules:

1. **Contracts live next to their producer.** A copy goes in `contracts/` only when a consumer in another language or deployable needs it. Every copy is generated, and CI regenerates it and fails on a diff:
   - The feature catalog stays in `application/training/feature_catalog/`, because the training image and the scoring Bento package it from there; generated schema files go into the Feast and Flink contexts ([E2 Feature parity](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity)).
   - The OpenAPI schema is generated from the API into `contracts/openapi/`.
   - The realm exports stay with the identity manifests.
2. **Consumers build against the current commit.** There is no internal versioning between packages in this repo (one-version rule). Versions exist where artifacts leave the repo: image digests, MLflow model versions and feature-set digests.
3. **No secret in Git, in any environment.** Overlays reference Secret names only. `make k8s-secrets` creates them from local environment variables. External Secrets or Sealed Secrets is a follow-up, recorded in the risk acceptance ([E9 Security baseline](../02-product/epics.md#e9-security-baseline)).
4. **Build once, promote digests.** Images are tagged with the git SHA. An overlay change that pins new digests is the release ([E16 UAT and release](../02-product/epics.md#e16-uat-and-release-readiness)).
5. **Ownership by path.** `.github/CODEOWNERS` maps paths to the role that reviews them (data engineering: `platform/data/`, `application/flink/`; data science: `application/training/`, `notebook/`; platform: `platform/`, `portals/`; risk: `application/authz/`, decision policy). Today one person holds every role, so the file documents intent and enables required reviews once there is a team.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Separate repo per portal | Independent release cadence | API and portal changes need coordinated PRs and version pinning; version skew between the generated client and the API |
| Separate GitOps config repo | Clean separation of deploy rights | Overkill for one team; a second place to change for every release |
| Root `contracts/` for every contract, including the feature catalog | One place to look | Breaks the Docker build contexts that package the catalog; the producer would no longer own its contract |
| Helm charts per service | Templating, packaging | More indirection than overlays need; the vendored charts were just removed (Tier A) |

## Consequences

### Positive

- One pull request changes the API, its contract and both portals together, and CI proves they agree.
- Environments differ only in overlays, so UAT is the same manifests as dev with different values.
- Releases are reproducible from a commit and a list of digests.

### Negative

- Two toolchains in one repo (Python, Node). `make check` runs both.
- Path-filtered builds are needed to keep CI fast once CI exists.

### Risks

- If the portals are later built by a separate team with its own release cadence, revisit this ADR.
