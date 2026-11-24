# Handoff packages

A handoff package is what a developer receives to build one epic. It links the work back to the [business outcome](../01-business/business-outcomes.md) and the [epic](../02-product/epics.md), and forward to the exact files, contracts and tests. Diagrams come from the same sources as the as-built architecture:

- **C4** views come from [`architecture/c4/workspace.dsl`](../architecture/c4/workspace.dsl). Target views are named `T-<epic>-…`, and planned elements are drawn with a dashed green border.
- **UML** (class, state) and **sequence** diagrams are Mermaid, in the package itself. Shared domain diagrams are in [`architecture/domain-model.md`](../architecture/domain-model.md).

## Packages

| Epic | Package | Outcome | Size | Depends on |
|---|---|---|---|---|
| [E9 Security baseline](../02-product/epics.md#e9-security-baseline) | [Security baseline](E9-security-baseline.md) | [O7 Data protection](../01-business/business-outcomes.md#o7-applicant-data-is-protected) | S | none |
| [E2 Feature parity](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity) | [Feature catalog and parity](E2-feature-catalog-and-parity.md) | [O3 Risk quality](../01-business/business-outcomes.md#o3-we-lend-to-good-risks-and-decline-bad-ones), [O4](../01-business/business-outcomes.md#o4-lending-is-fair) | M | none |
| [E3 Exactly-once readiness](../02-product/epics.md#e3-exactly-once-application-readiness) | [Exactly-once readiness](E3-exactly-once-readiness.md) | [O1 Fast answer](../01-business/business-outcomes.md#o1-applicants-get-an-answer-fast), [O5](../01-business/business-outcomes.md#o5-the-platform-scales-and-survives-failures) | M | none |
| [E6 Governed model](../02-product/epics.md#e6-fair-governed-credit-model) | [Fair, governed model](E6-fair-governed-model.md) | [O3 Risk quality](../01-business/business-outcomes.md#o3-we-lend-to-good-risks-and-decline-bad-ones), [O4](../01-business/business-outcomes.md#o4-lending-is-fair), [O6](../01-business/business-outcomes.md#o6-model-and-platform-changes-ship-safely) | M | [E2 Feature parity](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity) |
| [E7 Model promotion](../02-product/epics.md#e7-automated-traceable-model-promotion) | [Model lineage and reproducibility](E7-model-lineage.md) | [O6 Safe change](../01-business/business-outcomes.md#o6-model-and-platform-changes-ship-safely), [O8 Accountable](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) | M | [E6](../02-product/epics.md#e6-fair-governed-credit-model), [E2](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity) |
| [E5 Decision delivery](../02-product/epics.md#e5-decision-delivery-and-status-tracking) | [Decision delivery](E5-decision-delivery.md) | [O1 Fast answer](../01-business/business-outcomes.md#o1-applicants-get-an-answer-fast), [O2](../01-business/business-outcomes.md#o2-every-application-ends-in-a-clear-decision) | M | [E3 Exactly-once readiness](../02-product/epics.md#e3-exactly-once-application-readiness) |
| [E11 Identity and access](../02-product/epics.md#e11-identity-and-access) | [Identity and access](E11-identity-access.md) | [O7 Data protection](../01-business/business-outcomes.md#o7-applicant-data-is-protected), [O8](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) | M | [E9 Security baseline](../02-product/epics.md#e9-security-baseline), [E5](../02-product/epics.md#e5-decision-delivery-and-status-tracking) |
| [E13 Audit trail](../02-product/epics.md#e13-audit-trail) | [Audit trail](E13-audit-trail.md) | [O8 Accountable](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) | M | [E11 Identity and access](../02-product/epics.md#e11-identity-and-access), [E5](../02-product/epics.md#e5-decision-delivery-and-status-tracking) |
| [E14 Explainability](../02-product/epics.md#e14-explainability) | [Explainability](E14-explainability.md) | [O2 Clear decision](../01-business/business-outcomes.md#o2-every-application-ends-in-a-clear-decision), [O8](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) | M | [E6 Governed model](../02-product/epics.md#e6-fair-governed-credit-model), [E5](../02-product/epics.md#e5-decision-delivery-and-status-tracking), [E2](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity) |
| [E12 Portals](../02-product/epics.md#e12-staff-and-applicant-portals) | [Staff and applicant portals](E12-portals.md) | [O1 Fast answer](../01-business/business-outcomes.md#o1-applicants-get-an-answer-fast), [O7](../01-business/business-outcomes.md#o7-applicant-data-is-protected), [O8](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) | L | [E11 Identity and access](../02-product/epics.md#e11-identity-and-access), [E5](../02-product/epics.md#e5-decision-delivery-and-status-tracking), [E14](../02-product/epics.md#e14-explainability), [E13](../02-product/epics.md#e13-audit-trail) |
| [E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover) | [Resilience and failover](E15-resilience-failover.md) | [O5 Scale and survive](../01-business/business-outcomes.md#o5-the-platform-scales-and-survives-failures) | L | [E3 Exactly-once readiness](../02-product/epics.md#e3-exactly-once-application-readiness), [E5](../02-product/epics.md#e5-decision-delivery-and-status-tracking), [E8](../02-product/epics.md#e8-reliable-delivery-and-operations), [E11](../02-product/epics.md#e11-identity-and-access) |
| [E16 UAT and release](../02-product/epics.md#e16-uat-and-release-readiness) | [UAT and release readiness](E16-uat-release.md) | [O6 Safe change](../01-business/business-outcomes.md#o6-model-and-platform-changes-ship-safely), [O7](../01-business/business-outcomes.md#o7-applicant-data-is-protected) | M | [E11 Identity and access](../02-product/epics.md#e11-identity-and-access)–[E15](../02-product/epics.md#e15-resilience-and-failover) |

Cross-cutting: [feature governance plan](feature-governance-plan.md) ([E2 Feature parity](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity), [E6](../02-product/epics.md#e6-fair-governed-credit-model)), [threat model](../security/threat-model.md), [release checklist](../release/checklist.md), [UAT sign-off template](../release/uat-signoff-template.md).

## Definition of Ready (a package can be picked up when…)

- [ ] The outcome and KPI it moves are named, with the baseline.
- [ ] Scope in and out are explicit.
- [ ] The as-built C4 view and the target C4 view both exist and validate.
- [ ] The module interface is drawn as a UML class diagram. Behaviour over time is drawn as a sequence diagram, and stateful behaviour as a state machine.
- [ ] Every data contract that changes (event, table, config, file) is written out with an example.
- [ ] Every acceptance criterion maps to at least one named test at a named layer.
- [ ] Rollout, rollback and the signal that says it worked are written down.
- [ ] Open questions have an owner, or are explicitly deferred.

## Definition of Done

- [ ] Acceptance tests pass locally with `make check` (CI when available).
- [ ] The C4 model is updated: the `Planned` tag is removed from built elements, findings are closed in `07-findings.md`, and SVGs are regenerated.
- [ ] Docs touched by the change are updated in the same PR. An ADR is added if a decision was made.
- [ ] No new dead code: `ruff --select F` and `vulture --min-confidence 80` are clean for touched paths.

## Package template

```markdown
# E<n>: <name>

| Epic | Outcome / KPI | Baseline → target | Size | Depends on |

## 1. Why
## 2. Scope (in / out)
## 3. Today (as-built C4 view + current sequence)
## 4. Target design
### 4.1 C4 (target view)
### 4.2 Module interface (UML class)
### 4.3 Behaviour (sequence; state machine if stateful)
## 5. Data contracts
## 6. Change list (files)
## 7. Acceptance criteria → tests
## 8. Test plan by layer
## 9. Rollout, rollback, observability
## 10. Risks and open questions
```
