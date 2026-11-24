# Release go/no-go checklist

Copy this file to `docs/release/<version>.md` for each release candidate, fill every row with a link to its evidence, and get it signed. **A release ships only when every gate is ticked or has a written, signed exception.** The process is described in [E16](../03-handoff/E16-uat-release.md).

| Field | Value |
|---|---|
| Release candidate | `<version>` |
| Image digests | `reports/<rc>/digests.txt` |
| Model version / feature set | `credit_risk_model vN` / `<set version>` `<sha256>` |
| Release manager | |
| Date | |

## 1. Build and tests

| # | Gate | Evidence | ✓ |
|---|---|---|---|
| 1.1 | Unit and integration tests pass (`make check`) | test report | ☐ |
| 1.2 | Portal unit tests and Playwright journeys pass against UAT ([E12 Portals](../02-product/epics.md#e12-staff-and-applicant-portals)) | Playwright report | ☐ |
| 1.3 | Authorization matrix suite passes, including IDOR and separation-of-duties cases ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access)) | test report | ☐ |
| 1.4 | No dead code in touched paths: `ruff --select F`, `vulture --min-confidence 80` | log | ☐ |
| 1.5 | Every image is referenced by digest; none uses `:latest` | `digests.txt` | ☐ |

## 2. Model and decisions

| # | Gate | Evidence | ✓ |
|---|---|---|---|
| 2.1 | Model passed the registration gate: AUC ≥ Production − 0.005, floor 0.72 ([E6 Governed model](../02-product/epics.md#e6-fair-governed-credit-model)) | MLflow run | ☐ |
| 2.2 | No protected feature in the feature set; `dir_gender` reported; `fairness_review_required` resolved by the risk owner ([E6 Governed model](../02-product/epics.md#e6-fair-governed-credit-model)) | model card | ☐ |
| 2.3 | Explanations: additivity check passes; no protected or proxy reason codes; stability check passed or reviewed ([E14 Explainability](../02-product/epics.md#e14-explainability)) | test report, model card | ☐ |
| 2.4 | Decision policy bands match the active, second-approved policy change ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access)) | `policy_change` row | ☐ |
| 2.5 | Training–serving parity tests pass on the golden set ([E2 Feature parity](../02-product/epics.md#e2-feature-engineering-with-trainingserving-parity)) | test report | ☐ |

## 3. Security

| # | Gate | Evidence | ✓ |
|---|---|---|---|
| 3.1 | Threat model reviewed for this release; new risks have owners | [threat model](../security/threat-model.md) review note | ☐ |
| 3.2 | gitleaks: no findings | report | ☐ |
| 3.3 | SAST: `bandit` (Python) and `eslint-plugin-security` (TypeScript): no high | reports | ☐ |
| 3.4 | Dependencies: `pip-audit` and `npm audit --omit=dev`: no high or critical without a signed exception | reports | ☐ |
| 3.5 | Images: `trivy image`: no critical; highs have an exception | report | ☐ |
| 3.6 | ZAP baseline against both portals in UAT: no high | report | ☐ |
| 3.7 | Staff realm enforces TOTP; customers realm requires verified email; token lifetimes as designed ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access)) | realm export diff | ☐ |
| 3.8 | TLS on both ingress hosts; HSTS present | ZAP report or `curl -I` | ☐ |
| 3.9 | NetworkPolicies: default deny in every application namespace, explicit allows only | `kubectl get netpol -A` | ☐ |
| 3.10 | Logs contain no applicant names, dates of birth, phone numbers or tokens (sample of 1,000 lines) | log sample check | ☐ |
| 3.11 | Secrets come from Kubernetes Secrets created at deploy time; none in git or images | gitleaks + image scan | ☐ |

## 4. Resilience and operations

| # | Gate | Evidence | ✓ |
|---|---|---|---|
| 4.1 | Failover drill passed in the last 30 days for scoring, one Kafka broker and the ops DB primary: `lost = 0`, `auto_approved_during_fault = 0` ([E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover)) | drill reports | ☐ |
| 4.2 | Restore drill passed in the last 30 days: RPO ≤ 5 min, RTO ≤ 15 min ([E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover)) | restore report | ☐ |
| 4.3 | Load test at 30 RPS for 10 min meets the [O1 Fast answer](../01-business/business-outcomes.md#o1-applicants-get-an-answer-fast) and [O5](../01-business/business-outcomes.md#o5-the-platform-scales-and-survives-failures) targets | `tests/test_load/RESULTS.md` entry | ☐ |
| 4.4 | Alerts exist and were seen firing in a drill: consumer lag, DLQ growth, `audit_chain_ok`, under-replicated partitions, review queue > 50 | Grafana and alert screenshots | ☐ |
| 4.5 | Runbooks current: scoring down, Kafka broker lost, DB failover, Keycloak down, DLQ re-drive | `docs/runbooks/` | ☐ |
| 4.6 | Rollback plan written: previous digests and the previous model version | this file, §6 | ☐ |

## 5. Audit and acceptance

| # | Gate | Evidence | ✓ |
|---|---|---|---|
| 5.1 | An auditor reconstructed one decision end to end in ≤ 5 min; hash chain verified ([E13 Audit trail](../02-product/epics.md#e13-audit-trail)) | UAT-10 evidence | ☐ |
| 5.2 | UAT exit criteria met: 0 open Sev 1/2, ≤ 5 Sev 3 with owners | defect list | ☐ |
| 5.3 | UAT sign-off record signed by the product owner | [sign-off record](uat-signoff-template.md) copy | ☐ |
| 5.4 | SME review of 50 decisions completed; disagreements triaged | UAT-12 evidence | ☐ |

## 6. Rollback plan

| Item | Previous | New |
|---|---|---|
| Image digests | | |
| Model version | | |
| Feature set | | |
| Database migrations | backward compatible? yes / no (if no, describe) | |

## 7. Exceptions

| Gate | Reason | Compensating control | Expires | Approved by |
|---|---|---|---|---|

## 8. Decision

| Decision | Name | Role | Date |
|---|---|---|---|
| Go / No-go | | Release manager | |
| | | Risk owner | |
| | | Security | |
