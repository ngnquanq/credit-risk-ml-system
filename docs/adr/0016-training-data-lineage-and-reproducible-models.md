# ADR-0016: Every model run records where its data came from; the data is kept only for models that serve

## Status

Proposed

## Date

2026-11-24

## Deciders

Project owner as solution architect. To be reviewed by the roles that own model risk and compliance before it is accepted. Individual names were not recorded.

## Serves

- **Outcomes:** [O6 Safe change](../01-business/business-outcomes.md#o6-model-and-platform-changes-ship-safely), [O8 Accountable](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable), [O3 Risk quality](../01-business/business-outcomes.md#o3-we-lend-to-good-risks-and-decline-bad-ones)
- **Epics:** [E7 Model promotion](../02-product/epics.md#e7-automated-traceable-model-promotion) (features E7.1, E7.3, E7.4), [E6 Governed model](../02-product/epics.md#e6-fair-governed-credit-model), [E13 Audit trail](../02-product/epics.md#e13-audit-trail)
- **Quality attributes:** Auditability, reproducibility, privacy (keep as little personal data as possible), cost

## Context

A credit decision must be defensible later. Someone will ask which model made it, and which data that model learned from. If the source tables change after training, the answer is lost unless something was recorded at training time.

**Today.** [E7.1](../02-product/epics.md#e7-automated-traceable-model-promotion) promises the tags `git_commit` and `data_snapshot_id` on every version, but no training code sets them. The training log holds the feature-set digest and the feature list, and nothing about the data itself. The export target in the `Makefile` writes one snapshot to a fixed path (`ds=2025-09-19`) and overwrites it, so even that file cannot say which model used which data.

**Forces.**
- Keeping a full copy of the training data for every run is costly. Object stores keep a whole object per version, not a difference (Reis and Housley, *Fundamentals of Data Engineering*, ch. 6). It also multiplies copies of credit data, which makes erasure obligations harder (same book, ch. 7).
- DVC avoids storing the same file twice, but a file whose content changed is a new full object. It is a pointer in git to a copy, not a way to avoid copies.
- Table formats such as Iceberg and Delta keep history without copying the table, but old snapshots disappear when they are cleaned up (examples in the vendor documents: 5 to 7 days) unless a tag or branch pins them. ClickHouse can read Iceberg time travel, but only for tables stored as Iceberg; its own tables have no user-facing time travel (our reading, not checked against its documentation).
- A query by event time alone is not enough when a source row can be corrected after the model trained. The same query a year later returns the corrected row, not what the model saw. Reproducing needs both event time and the time the system learned the row, or a copy.
- Four levels of assurance are in play: **traceable** (we know what was used), **change-detectable** (a hash or a profile shows a difference), **reproducible** (the same inputs give the same model) and **auditable** (someone outside can check). Provenance, tamper detection, reproducible builds and accountability each come from different sources (NIST SP 800-218, *Building Secure and Reliable Systems* ch. 14, NIST AI 100-1).
- How long a regulator expects model artefacts to be kept is **not stated in the sources we read**. NIST AI 100-1 does not name a period.

## Decision

1. **Every training run records a lineage record** in its MLflow run, copied as tags on the registered version. It holds the dataset digest, row and column counts, the event-time window and the system cut-off, the git commit and run id of the dbt models that built the data, the feature-set digest, the git commit and image digest of the training code, the seed and the library versions. A **data profile** (per-feature count, mean, spread, range, null rate, quantiles) is attached as an artifact. The run's de-identified training frame is kept only in a **staging area that expires** (the period is an open question), so a run promoted soon after training can be frozen exactly. Nothing else of the data is kept for an ordinary run.
2. **A version that is promoted to serve has its training data frozen.** Its staged frame is moved to permanent object storage as a de-identified extract (opaque ids, no direct identifiers), written once, and its digest must equal the digest in the lineage record. If the staging copy has expired, the frame is rebuilt from the recorded query and cut-offs, and promotion goes on only if the digest matches. Otherwise the model is retrained. Promotion without a matching extract does not proceed to a build.
3. The staged or frozen frame is the only exact copy. Where a source table can be corrected in place, a rebuild may return different data. The digest then differs, which is reported as "the data changed", and the model is retrained instead of promoted.
4. The training query reads tables that are appended to, with event time and load time on every row, so a cut-off on both is meaningful. Where that does not hold, the table is listed as mutable in the lineage record.
5. The mechanism for the frozen extract (a Parquet file tracked by DVC, or an Iceberg tag) is replaceable. The lineage record and the digest check do not change if it is.
6. The fixed-path snapshot export stops being treated as lineage. It remains, if needed, a scratch copy.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Full snapshot for every run | Simple; exact rebuild of every run | Cost grows with every retrain; many copies of credit data; hard to erase |
| DVC for every run | Git-linked, light to run, no database | Still a full copy for each changed file; per-file overhead if the data becomes many files |
| Time travel in a table format, no pinning | No copies; query in place | History is lost when old snapshots are cleaned; needs the training tables to be Iceberg or Delta, which the current warehouse does not write |
| Hash and profile only | No stored data, so nothing to erase; nearly free | Cannot rebuild data or diff rows; only detects change |
| lakeFS | Branches of the data, no copy | Not evaluated: the sources give no detail, and the claim that it now owns DVC comes from one vendor source |
| **Lineage record for every run, short-lived staging, permanent data only for serving models (chosen)** | Keeps the cost and the personal data small; the models that decide real credit can be rebuilt exactly | Rows of a run that was never promoted cannot be compared once its staging copy expires, only its profile and digest |

## Consequences

### Positive
- A serving model can be traced to its code, its data build and its feature set, and its training data can be rebuilt and checked against a digest.
- Two runs can be compared by digest (same or not) and by profile (where they differ).
- The number of copies of credit data stays small.

### Negative
- A discarded run's data cannot be rebuilt, so "why was this retrain not chosen" is answered from its metrics and profile, not by re-running it.
- Promotion gains a step, and a job that freezes the extract.
- A staging area holds temporary copies of de-identified credit data until they expire.

### Risks
- **De-identification fails.** The frozen extract is a new copy of credit data. A check on its columns is required, and which columns the training frame holds today has not been checked.
- **Retention periods unknown.** Compliance has to set how long frozen extracts are kept (until then nothing is deleted automatically) and how long the staging area keeps a run's frame. Both decisions need an owner.
- **Mutable sources.** If the warehouse tables are rewritten in place, digests will differ between runs on the "same" window. That is detected, not prevented.
- The digest depends on a stable row order and column order. The method is fixed in the handoff package.

## Compliance

Each line names a check that is **not yet built**. The handoff package lists them against acceptance criteria.
- Registration fails when the lineage record or a required tag is missing.
- A staged frame is deleted when its period ends.
- The same data gives the same digest whatever the row order.
- The build after a promotion fails when the frozen extract is missing or its digest differs.
- A test fails when the frozen extract contains a column on the direct-identifier list.

## Notes

- Author: project owner with an AI assistant. Design in the [E7 model lineage package](../03-handoff/E7-model-lineage.md).
- Sources read through the project notebook, with the passages **not re-verified** against the books: Wilson, *Machine Learning Engineering in Action* (ch. 14 and 16, on losing the ability to recreate a model and on logging what a run used); Reis and Housley, *Fundamentals of Data Engineering* (ch. 5 to 8, on event, ingestion and processing time, slowly changing dimensions, versioning cost, table history, privacy and erasure); *Building Secure and Reliable Systems* (ch. 14, reproducible builds and provenance); NIST SP 800-218; NIST AI 100-1. Public documents consulted: MLflow dataset tracking, Iceberg and Delta retention, DVC, ClickHouse's Iceberg function.
- **Our inference, not in the sources:** the two-level split between ordinary and serving runs; freezing data at promotion; keeping the extract de-identified; treating the table-format tag and DVC as interchangeable.
- Related: [ADR-0009](0009-model-training-and-promotion-pipeline.md) (the promotion trigger is unchanged), [ADR-0003](0003-feast-as-feature-store.md), [ADR-0014](0014-applicant-personal-data-and-opaque-ids.md) (opaque ids).
- When accepted, update the `ModelVersion` class in [domain-model](../architecture/domain-model.md) and the snapshot design in the [E6 package](../03-handoff/E6-fair-governed-model.md).
