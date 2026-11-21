# Handoff packages

A handoff package is what a developer receives to build one epic. It links the work back to the [business outcome](../01-business/business-outcomes.md) and the [epic](../02-product/epics.md), and forward to the exact files, contracts and tests. Diagrams come from the same sources as the as-built architecture:

- **C4** views come from [`architecture/c4/workspace.dsl`](../architecture/c4/workspace.dsl). Target views are named `T-<epic>-…`, and planned elements are drawn with a dashed green border.
- **UML** (class, state) and **sequence** diagrams are Mermaid, in the package itself. Shared domain diagrams are in [`architecture/domain-model.md`](../architecture/domain-model.md).

## Packages

| Epic | Package | Outcome | Size | Depends on |
|---|---|---|---|---|
| E9 | [Security baseline](E9-security-baseline.md) | O7 | S | none |
| E2 | [Feature catalog and parity](E2-feature-catalog-and-parity.md) | O3, O4 | M | none |
| E3 | [Exactly-once readiness](E3-exactly-once-readiness.md) | O1, O5 | M | none |
| E6 | [Fair, governed model](E6-fair-governed-model.md) | O3, O4, O6 | M | E2 |
| E5 | [Decision delivery](E5-decision-delivery.md) | O1, O2 | M | E3 |

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
