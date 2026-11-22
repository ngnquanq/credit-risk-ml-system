# C4 architecture model

The architecture of the Credit Risk Decisioning Platform in [Structurizr DSL](https://docs.structurizr.com/dsl). The original Minikube views record the baseline checked on 2026-11-21 (commit `7605340)), before Streamlit was retired. The portal views document the replacement design.

| Path | What it is |
|---|---|
| [`workspace.dsl`](workspace.dsl) | **Source of truth.** Model (8 people/systems, 51 containers, 39 components), 31 views, deployment environment, styles. |
| [`docs/`](docs/) | Narrative sections, embedded in Structurizr via `!docs` and readable on GitHub (Mermaid renders natively). |
| [`docs/images/`](docs/images/) | SVGs of every view, generated from the DSL. Do not edit by hand. |

## Read in this order

1. [Overview](docs/01-overview.md): scope, view index, notation, key numbers
2. [Context and containers](docs/02-context-and-containers.md): L1 and L2, with a catalogue of every container
3. [Components](docs/03-components.md): L3 for the custom-code containers
4. [Runtime sequences](docs/04-runtime-sequences.md): 9 Mermaid sequence diagrams with payloads, retries and failure branches, plus a failure-mode table
5. [Data flow](docs/05-data-flow.md): DFDs, topic catalogue, message shapes, store catalogue, training-vs-serving feature lineage
6. [Deployment](docs/06-deployment.md): namespaces, workloads, deploy order, ports, resources, scaling limits
7. [Findings](docs/07-findings.md): 18 places where the build departs from the design, each tagged on the diagrams

## Views

| Level | Keys |
|---|---|
| Landscape / context | `L0-Landscape`, `L1-Context` |
| Containers | `L2-All`, `L2-1-Intake`, `L2-2-Feature-Pipeline`, `L2-3-Scoring`, `L2-4-Warehouse`, `L2-5-Model-Lifecycle`, `L2-6-Ops`, `L2-7-Kafka-Topology` |
| Components | `L3-API`, `L3-Flink`, `L3-Bureau-Service`, `L3-DWH-Service`, `L3-Feast-Materialiser`, `L3-Scoring-Service`, `L3-Training-Pipeline`, `L3-dbt` |
| Dynamic | `D1-Submit-Application`, `D1a-API-Submission`, `D2-Feature-Engineering`, `D3-Score-Application`, `D3c-Feast-Coordination`, `D3s-Scoring-Request`, `D4-Upload-Document`, `D5-Warehouse-Bootstrap`, `D6-Train-and-Register`, `D7-Promote-to-Serving`, `D8-Load-Test` |
| Deployment | `Deploy-Minikube-All`, `Deploy-Minikube-RealTime` |

## Formats used, and why

| Concern | Format | Reason |
|---|---|---|
| Structure (C4 L1–L3, deployment) | Structurizr DSL | One model, many consistent views. Elements are defined once. |
| Runtime "which elements take part" | Structurizr dynamic views | Stay in sync with the model, because they fail validation if a relationship does not exist |
| Runtime detail (payloads, alt/loop/par, failures) | Mermaid `sequenceDiagram` | Dynamic views cannot express alternatives or loops. Mermaid renders on GitHub. |
| Data flow | Mermaid `flowchart` DFDs + tables | C4 arrows show dependency, not data direction |

## View, validate, export

Run these from this directory. Port 8081 is used so it does not collide with another Structurizr instance on 8080.

```bash
# Browse interactively (http://localhost:8081, workspace 1)
docker run -it --rm -p 8081:8080 -v "$PWD:/usr/local/structurizr" structurizr/structurizr local

# Validate. NOTE: exits 0 even on failure, so check that it prints no ERROR line
docker run --rm -v "$PWD:/usr/local/structurizr" structurizr/structurizr validate -w /usr/local/structurizr/workspace.dsl

# Model quality checks (one expected warning: decisions are linked, not imported, see below)
docker run --rm -v "$PWD:/usr/local/structurizr" structurizr/structurizr inspect -w /usr/local/structurizr/workspace.dsl

# Regenerate docs/images/*.svg (this Structurizr build cannot export SVG directly, so go through PlantUML)
OUT=$(mktemp -d)
docker run --rm -v "$PWD:/usr/local/structurizr" -v "$OUT:/out" structurizr/structurizr \
  export -w /usr/local/structurizr/workspace.dsl -f plantuml/structurizr -o /out
find "$OUT" -name '*-key.puml' -delete
docker run --rm -e PLANTUML_LIMIT_SIZE=16384 -v "$OUT:/data" -w /data plantuml/plantuml -tsvg -charset UTF-8 "*.puml"
for f in "$OUT"/structurizr-*.svg; do b=$(basename "$f" .svg); cp "$f" "docs/images/${b#structurizr-}.svg"; done
```

Other export formats from the same command: `-f mermaid` (C4 views as Mermaid flowcharts), `-f plantuml/c4plantuml`, `-f websequencediagrams` (dynamic views), `-f json`.

## Conventions

- **Identifiers** are hierarchical (`crs.api.routes`). Kafka topics are containers tagged `Topic`, so every producer and consumer is an explicit relationship.
- **Relationship direction is dependency** (who initiates). Consumers point at the topic they read. Data direction is in [Data flow](docs/05-data-flow.md).
- **Tags carry meaning.** `Risk` (red outline) works but is fragile or wrong. `Gap` (dashed red) is missing. `Optional`/`Unused` is deployed but inactive. Each `Risk`/`Gap` maps to an ID in [Findings](docs/07-findings.md).
- **Element `properties`** hold `source` (code path) and `k8s` (workload). They are visible in the Structurizr UI.
- **ADRs** stay in [`docs/adr/`](../../adr/) and are linked rather than imported with `!adrs`, because the Docker mount only sees this directory. Copying them would create a second copy to keep in sync.

## Keeping it true

When you change code that adds or removes a container, topic, consumer group, Kafka key or deployment knob, update `workspace.dsl` in the same commit, re-run validate, and regenerate the SVGs. When you fix a finding, remove its `Risk`/`Gap` tag and mark it in `docs/07-findings.md`.
