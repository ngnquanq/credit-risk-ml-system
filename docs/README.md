# Documentation

Read top-down: why → what → how it is built → what to build next.

| Step | Path | What it is |
|---|---|---|
| 1. Why | [`01-business/business-outcomes.md`](01-business/business-outcomes.md) | Problem, outcomes [O1 Fast answer](01-business/business-outcomes.md#o1-applicants-get-an-answer-fast)–[O8](01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) with KPIs (baseline → target), stakeholders, impact map |
| 2. What | [`02-product/epics.md`](02-product/epics.md) | Epics [E1 Intake](02-product/epics.md#e1-application-intake-and-document-capture)–[E16](02-product/epics.md#e16-uat-and-release-readiness), status, user stories, acceptance criteria, delivery order |
| 3. How it is built | [`architecture/c4/`](architecture/c4/README.md) | C4 model (as-built + planned), sequences, data flow, deployment, findings |
| | [`architecture/domain-model.md`](architecture/domain-model.md) | Vocabulary, UML class diagrams, lifecycle state machines |
| 4. Build next | [`03-handoff/`](03-handoff/README.md) | Handoff packages per epic (C4 target view, UML, sequences, contracts, tests) |
| 5. Release | [`release/checklist.md`](release/checklist.md), [`release/uat-signoff-template.md`](release/uat-signoff-template.md) | Go/no-go gates with evidence; UAT record ([E16 UAT and release](02-product/epics.md#e16-uat-and-release-readiness)) |
| Security | [`security/threat-model.md`](security/threat-model.md) | STRIDE per trust boundary for the target design |
| Decisions | [`adr/`](adr/README.md) | Architecture Decision Records |
| Reference | [`01-business/business-constraints.md`](01-business/business-constraints.md), [`01-business/data-definition.md`](01-business/data-definition.md) | Pre-screening rules ([E10 Pre-screening](02-product/epics.md#e10-pre-screening-business-rules)), feature sources |
| Modeling | [Credit risk modeling references](01-business/credit-risk-modeling-references.md) | Datasets, calibration, selection bias, AutoML smoke test |
| History | [`history/`](history/README.md) | Superseded status logs (not maintained) |
