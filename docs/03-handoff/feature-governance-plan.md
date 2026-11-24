# Feature governance plan

## Where definitions and values live

Start with a versioned catalog in this repository. Put reusable definitions under `feature_catalog/definitions/` grouped by producer domain and ordered model selections under `feature_catalog/sets/`. Use YAML validated by a typed schema. A model set references feature IDs and revisions, plus the preprocessing policy for that model. A catalog entry describes what a feature means, where its values come from and how to interpret them. Flink and dbt continue to execute transformations. Feast continues to publish and retrieve online and historical features where supported. The existing Feast registry is the deployed metadata for each environment. [Feast Registry](https://docs.feast.dev/master/getting-started/components/registry)

Package a resolved manifest and digest, or an equivalent immutable reference with a retained artifact, with each model. The manifest maps ordered training column names to exact Feast view and field references. Record the catalog commit, feature-set version, snapshot identifier and preprocessing configuration alongside the model in MLflow. Serving loads the model's pinned contract at startup and checks that its dependencies are available. The scoring request path continues to use Feast for values. Feast Feature Services can group retrieval references by model version once the registered views support them. [Feast feature retrieval](https://docs.feast.dev/master/getting-started/concepts/feature-retrieval)

## Contract and controls

| Control | What it checks |
|---|---|
| Definition schema | Stable ID, revision, owner, meaning, dtype, unit, entity key, source lineage, transform reference, event and availability timestamps where relevant, missing and sentinel semantics, freshness and data classification |
| Model set schema | Ordered references resolve exactly once. Join keys and labels stay outside model inputs. Restricted fields are rejected for new approved sets according to policy. Model-specific imputation and encoding are explicit. |
| Compatibility | A breaking change to meaning, units, type, timestamp semantics or defaults creates a new revision. Adding a feature to the catalog leaves consumers pinned to their existing sets. Adding one to a model set creates a new set version and requires retraining. |
| CI and promotion | Validate schema, references and policy. Test generated or declared schemas against producer and Feast metadata. Run offline/online parity on 50 golden cases as defined in [E2 Feature parity](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity). Check that no value uses information unavailable at decision time. Publish only approved changes to staging and production via a restricted CI identity. |
| Runtime and rollback | Monitor freshness, missing rates and schema mismatches by feature set. Retain old definitions and values for active models and the rollback window. Roll back the model together with its compatible feature set. |
| Deprecation | List affected models and owners, announce a retirement window, and remove a revision after active and rollback consumers have migrated. |

Point-in-time correctness requires checking both the feature event time and when the value was actually available. A historical join on event time alone cannot establish the latter. [Feast point-in-time retrieval](https://docs.feast.dev/master/getting-started/concepts/feature-retrieval)

## Team workflow

1. **Data Engineering** owns the definition, transform, lineage and producer quality checks. A feature PR includes sample outputs, impact on downstream models and a backfill plan if needed.
2. **Data Science** owns model feature sets and evaluation. It proposes feature selection changes, runs comparisons using a frozen holdout and logs the resolved set with the candidate model.
3. **ML Platform** owns validation tooling, release automation, Feast application, service identities and rollback. Use path ownership and required checks for catalog and deployment changes.
4. **Risk/Governance** reviews restricted or sensitive inputs and material changes to models used in decisions. Record approvals and evidence in the PR or model review record.

For changes affecting multiple teams, the definition owner proposes the change, the affected model owners review compatibility, and ML Platform deploys the approved manifest to staging. Data Science and Risk review model changes before promotion under the project's model policy.

## Delivery order

1. **Extract the current contract.** Inventory the 24 features and freeze a legacy feature set with the current order and behavior. Adapt CLI, notebook and Kubeflow to pass a resolved set to preprocessing. Compare old and new column order, transformations, predictions and metadata on a fixed fixture. Keep existing models loadable. Protected-feature removal is a separately evaluated model change under [E6 Governed model](../02-product/epics.md#e6-fair-governed-credit-model).
2. **Connect to producers and serving.** Map every feature to the dbt or Flink output and Feast reference. Validate schemas and add the [E2](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity) golden parity gate. Investigate discrepancies such as employment-day semantics in separately reviewed changes before requiring parity for promotion.
3. **Operate the lifecycle.** Publish immutable releases, enforce change ownership and staging gates, monitor freshness and nulls, and rehearse rollback. Test a new feature version alongside an existing model before retiring any old version.

Extract the catalog into a dedicated Git repository when multiple independently released products need to consume it or when ownership and permissions require a separate release process. Keep the same immutable artifact interface. Consider a metadata service when teams need cross-project discovery, lineage search or API access that Git and Feast cannot provide at the required scale.

## First rollout

The initial ordered set is [legacy-v1](../../contracts/feature_catalog/sets/legacy-v1.json). Its JSON format works in both training images using the Python standard library. The training package ships the set alongside the loader. Producer definitions and the Feast mapping are follow-up work.

- Local CLI accepts `--feature-set <version>`. When using notebook output as `--config`, it takes the recorded feature-set version and checks its digest.
- Notebook runs select a packaged set with `CRQ_FEATURE_SET=<version>`. Rerun tuning when changing the set or using an old cache without a digest.
- Kubeflow reads `feature_set_version` from `config_json`. The tuning result carries the digest and registration compares it with the selected set. Build both images from the same revision on Linux.
- Training logs the resolved manifest to MLflow as `model/feature_set.json` and records its version and digest in `feast_metadata.yaml`.

## Cross-check against Wilson

Source: Ben Wilson, *Machine Learning Engineering in Action* (Manning, 2022). Section numbers were checked against the book's table of contents. An earlier NotebookLM answer cited §1.4, which does not exist, and attached §8.1.3 and §14.3 to claims those sections do not make; those citations are removed.

| Claim in this plan | Support in the book |
|---|---|
| Keep one source of truth for data and features; do not bury data cleansing in model code | §14.1.2 "Check your data provenance", §14.1.3 "Find a source of truth and align on it", §14.1.4 "Don't embed data cleansing into your production code" |
| Move shared logic out of scripts into a structured, named module | §10.2 "Naming, structure, and code architecture" |
| Training–serving skew is a data-consistency problem; process matters more than tooling | §15.1.1 "Training and inference skew", §15.1.2 "A brief intro to feature stores", §15.1.3 "Process over technology" |
| Feature stores make features reusable across projects; the book's example uses the Databricks Feature Store with MLflow | §16.2.1 "What a feature store is used for", §16.2.2 "Using a feature store" |
| Track models and their artifacts in a registry | §8.1 "Logging: Code, metrics, and results", §16.1 "Artifact management" |
| Review catalog changes through branches and pull requests | §8.1.3 "Version control, branch strategies, and working with others" |
| Test transforms; monitor feature distributions after release | §9.4 "Using test-driven development for ML", §14.2 "Monitoring your features", §12.2 "Responding to drift" |
| Avoid a dedicated catalog service until reuse demands it | §13.1 "Elegant complexity vs. overengineering" |

The Git layout (definitions and ordered sets), the resolved manifest and its digest, and the team ownership split are design choices for this repository. The book does not prescribe them.
