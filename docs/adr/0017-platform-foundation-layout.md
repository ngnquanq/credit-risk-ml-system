# ADR-0017: `platform/foundation` holds what everything else runs on; service deployment config sits with the service

## Status

Accepted. Refines the part of [ADR-0015](0015-services-layout-high-cohesion-low-coupling.md) that said `platform/` is expected to become `infra/`.

## Date

2026-11-25

## Deciders

Project owner (solution architect).

## Serves

- **Outcomes:** [O6 Model and platform changes ship safely](../01-business/business-outcomes.md#o6-model-and-platform-changes-ship-safely)
- **Epics:** [E9 Security baseline](../02-product/epics.md), [E11 Identity and access](../02-product/epics.md)
- **Quality attributes:** modifiability, security (smaller blast radius for a change to shared parts)

## Context

`platform/core` held Keycloak and its realms, one Ingress, the loan-api ConfigMap, and three database files (`pgbouncer.ini`, `userlist.txt`, `init-ops-database.sql`) that nothing referenced. `platform/ops` held only the observability stack (logging, monitoring, tracing), not operations in general. Neither name told a reader what belongs there, and `core` collected whatever had no other home.

## Decision

1. **`platform/foundation/`** holds what other things run on, one sub-folder per concern: `identity/` (Keycloak, its database, realms, login theme) and `observability/` (`logging/`, `monitoring/`, `tracing/`). A new sub-folder is added only when something real needs it (for example a certificate issuer or network policy for the shared edge), not in advance.
2. **A service's own deployment config sits with the service.** The loan-api ConfigMap and its Ingress moved to `services/loan-api/deploy/api/` and are applied by that service's kustomization. The Ingress has one rule and one backend, so it is the API's routing, not a shared gateway.
3. **Stale, unreferenced files are deleted**, not moved: the three database files above (the running copies live in `platform/data/k8s/operational-db/`; the old init script also granted `REPLICATION` to the admin user, which the CDC role now replaces) and `platform/core/nginx.conf` (upstreams named after docker-compose containers, a 50 MB body limit for uploads that now go straight to object storage, and load balancing that ingress-nginx does).
4. `platform/data`, `platform/ml`, `platform/config` and `platform/environments` keep their places.

## Alternatives Considered

| Option | Why not |
|---|---|
| Keep `core` and `ops` | The names do not state a rule; `core` kept collecting stray files |
| Split `runtime` (identity, ingress) from `observability` | `runtime` would have held one folder and one file; once the Ingress went to the service, only `identity` remained |
| Move `environments/` out of `platform/` | Suggested by the notebook; costs more path changes for a gain not yet needed. Left for a later decision |

## Consequences

- A reader can tell from the path whether a file is shared (`foundation/`), a data tier (`data/`) or one service's (`services/<name>/deploy`).
- Every path that named `platform/core` or `platform/ops` changed (Makefile, overlays, tests, CODEOWNERS, handoff docs). Architecture C4 sources and older ADRs still show the old paths and are updated with their own changes.

## Compliance

The infrastructure tests (`tests/unit/infra`) scan `platform/foundation` and fail on a hard-coded host, topic or image outside the single sources. `lint-imports` is unaffected.

## Notes

**What the sources support.** The notebook (Richards and Ford, ch. 16 p. 237) separates infrastructure services such as logging, monitoring and authentication from business services; it warns that a common folder with only coincidental cohesion becomes a catch-all (ch. 3 pp. 40 to 41); Twelve-Factor and *Software Engineering at Google* (ch. 23) place a service's configuration with its release. **Not in any source:** the folder names, and treating observability as a soft dependency that deserves its own folder. Those are conventions chosen here.
