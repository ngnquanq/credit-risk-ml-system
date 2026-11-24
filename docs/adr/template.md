# ADR-XXXX: [Title: the decision, in a few words]

<!--
Write an ADR for an architecturally significant decision: one that changes a quality attribute (security,
scalability, reliability, modifiability) or the structure of the system, and is costly to change later.
Do not write one for internal class design or a library version. Keep it to one or two pages; it records a
decision, not the whole design (that is the handoff package). Once accepted it is not edited: a new decision
is a new ADR that supersedes this one.
Follow-up work does not live here. It goes into the epic's features, or into an enabler.
-->

## Status

[Proposed | Accepted | Rejected | Superseded by [ADR-XXXX](XXXX-new-decision.md)]

If this ADR replaces an earlier one, say "Supersedes ADR-XXXX" here and mark the old one "Superseded by this".

## Date

YYYY-MM-DD

## Deciders

[Roles, and names if they are recorded (for example solution architect, security architect).]

## Serves

- **Outcomes:** [O-x name](../01-business/business-outcomes.md)
- **Epics:** [E-y name](../02-product/epics.md)
- **Quality attributes:** [security, latency, modifiability, ...]

## Context

[The problem and the forces, stated objectively and without leaning toward the answer: business drivers, the
quality attributes at stake, and constraints.]

For a security decision, also name the threats it addresses (reference the [threat model](../security/threat-model.md)
and, where useful, the STRIDE category) and the policy or regulation behind it.

## Decision

[What we decided, in active voice: "We will ...". Direct and unambiguous.]

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|

## Consequences

### Positive

### Negative

### Risks

For a security decision, state the **residual risk**: what remains after this control, and whether anyone had to accept it.

## Compliance

[How we know the decision is being followed: the tests, checks or reviews that would fail if it were not.
Link them. For example a unit test, an import-linter contract, a CI gate, a review checklist.]

## Notes

[Metadata: author, approvers, links to the design (handoff package), and any later corrections such as moved paths.]
