# ADR-0013: Role-based visibility of customer data and explanations; officers do not decide

## Status

Accepted

## Date

2026-11-22

## Context

Staff need internal information about a customer to serve them: previous contracts with the lender, current exposure, repayment behaviour and a bureau summary. Unrestricted access to that information invites misuse, for example looking up neighbours or relatives. Separately, the platform now produces explanations ([E14 Explainability](../02-product/epics.md#e14-explainability)): plain-language reasons for applicants, and per-feature SHAP contributions with the score for experts. Three questions came up:

1. Which staff may see internal factors, and for which customers?
2. Should the loan officer take part in the decision outcome?
3. Who may see which layer of the explanation?

## Decision

**Internal factors (need to know).**
- A loan officer sees the customer profile only for an application they are handling, after the customer's consent to the bureau check is recorded.
- Looking up any other customer requires the exact citizen ID number and a purpose from a fixed list (co-applicant, guarantor, customer present at the branch). For files outside the officer's branch, it returns only the contract count and status.
- There is no name search and no browsing. Every view and lookup is audited with its purpose and reviewed monthly.

**Maker–checker.**
- The loan officer is the maker: they capture data, verify documents and identity, attach notes and flag concerns (suspected fraud, document mismatch). They cannot approve, reject or change an outcome.
- Underwriters decide manual reviews, and never on an application they submitted ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access)).

**Explanation tiers.**

| Role | Sees | Does not see |
|---|---|---|
| Applicant | Up to four principal reasons in plain language; what they can do next | Score, thresholds, contributions |
| Loan officer | The same reasons the applicant sees; documents to collect | Score, contributions, band thresholds |
| Underwriter | Score, band, per-feature contributions, model and feature-set version; evidence shown before the model explanation | (full view) |
| Risk manager | Global explanations and distributions; individual cases only through the review or audit flows | Browsing individual PII |
| Auditor | The decision as recorded (score, reasons, versions) and the audit timeline; read-only | (no edits) |

**Why officers do not see contributions.**
- An officer who knows which inputs move the score can coach an applicant to restate them until the application passes. This is gaming, a form of Goodhart's law.
- Officers often carry sales targets, a conflict of interest.

**Why the underwriter sees evidence first.** The screen order reduces automation bias, which is the habit of deferring to the model.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Officers see everything for their branch | Fewer clicks | Broad insider access to PII; no purpose limitation |
| Officers decide borderline cases | Faster for walk-in customers | Conflict of interest; no segregation of duties |
| Officers see full SHAP contributions | Can coach customers on documents | Enables gaming of inputs; contributions are easy to misread as causes |
| Nobody but auditors sees contributions | Least exposure | Underwriters decide without the model's reasoning |

## Consequences

### Positive

- Access to internal data is purpose-bound and auditable; misuse leaves a trail.
- Decisions on borderline cases are made by someone without a sales incentive and not the submitter.
- Each audience gets the explanation it can act on.

### Negative

- Officers sometimes need an underwriter to answer "why exactly" for a customer.
- The lookup flow adds a step for legitimate co-applicant checks.

### Risks

- A purpose list can be abused by always choosing "customer present". The monthly review of lookups per officer is the control; repeated lookups without a resulting application are flagged.
