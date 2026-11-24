# ADR-0012: Keycloak with two realms, and backend-for-frontend portals

## Status

Accepted

## Date

2026-11-22

## Deciders

Solution architect and security architect (the roles that own this area). Individual names were not recorded.

## Serves

- **Outcomes:** [O7 Data protection](../01-business/business-outcomes.md#o7-applicant-data-is-protected), [O8 Accountable](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable)
- **Epics:** [E11 Identity and access](../02-product/epics.md#e11-identity-and-access) (features F1 and F2), [E12 Portals](../02-product/epics.md#e12-staff-and-applicant-portals)
- **Quality attributes:** Security (authentication, session handling)

## Context

Applications arrive from two populations: lender staff entering applications for walk-in customers, and applicants applying online ([E1 Intake](../02-product/epics.md#e1-application-intake-and-document-capture), [E11](../02-product/epics.md#e11-identity-and-access)). Today nobody signs in (F-17). Staff need MFA and no self-registration; applicants need self-registration with a verified email. The web UI moves from Streamlit to TypeScript ([E12](../02-product/epics.md#e12-staff-and-applicant-portals)) and handles personal data, so tokens must not be exposed to browser JavaScript.

## Decision

- **Identity provider:** Keycloak, self-hosted in the cluster, with two realms:
  - `staff`: no self-registration, TOTP required, a `branch_id` attribute, and roles `loan_officer`, `underwriter`, `risk_manager`, `auditor` and `admin`.
  - `customers`: self-registration, verified email, role `applicant`.

  Realm exports are committed without secrets. A person belongs to exactly one realm.
- **Portals:** two Next.js apps act as backends-for-frontend.
  - Sign-in uses the authorization code flow with PKCE as a confidential client.
  - Tokens stay on the server; the browser holds only an httpOnly `__Host-` session cookie.
  - The portals call the API with the user's access token (token relay).
- **API:** verifies tokens (issuer allow-list, audience, RS256, cached JWKS) and asks a single policy module, `application/authz/policy.py`, which denies by default.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Microsoft Entra ID | Closest to a real bank's workforce IdP | Needs a tenant; not reproducible for someone cloning the repo |
| Auth0 / Okta free tier | Fast setup | External SaaS dependency for a demo; account-bound |
| One realm with a `type` attribute | Simpler configuration | Applicant and staff policies (MFA, registration) mix; one misconfiguration exposes staff roles to the public |
| SPA with PKCE and tokens in browser memory | Simplest frontend | Tokens reachable by any XSS; weaker for a page holding personal data |
| oauth2-proxy in front of a static SPA | Little auth code in the UI | Another component; less control over CSRF and session behaviour |

## Consequences

### Positive

- MFA for every staff account; applicant accounts cannot gain staff roles.
- No access or refresh token ever reaches the browser.
- Authorization decisions live in one tested module, and every denial is audited ([E13 Audit trail](../02-product/epics.md#e13-audit-trail)).

### Negative

- Keycloak and a session store are new stateful components ([E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover) covers their failure modes).
- A Node.js runtime to patch and scan.

### Risks

- Keycloak outage blocks new sign-ins; existing sessions survive until the 5-minute access token cannot be refreshed. Documented in [E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover).

## Compliance

- [`test_rejected_tokens`](../../tests/unit/api/test_token_verifier.py) fails if the API accepts a foreign issuer, a wrong audience, a token without MFA, a staff role from the customer realm, `alg=none` or HS256.
- `test_missing_token_is_401` in [`test_access_control.py`](../../tests/integration/api/test_access_control.py) fails if a route answers without a token.
- `expectNoTokenInBrowser` in the end-to-end specs ([applicant](../../portals/e2e-local/applicant.spec.ts), [staff](../../portals/e2e-local/staff.spec.ts)) fails if a token reaches the browser. They run on the local stack with `pnpm e2e:local`, not in CI.
- Checked by hand in UAT: that Keycloak asks a new staff member to set up TOTP.

## Notes

- Design: [E11 handoff package](../03-handoff/E11-identity-access.md) and [how sign-in and permissions work](../architecture/authn-authz.md).
- The sections Deciders, Serves, Compliance and Notes were added on 2026-11-24 to trace this decision to its outcomes and epics. The decision itself is unchanged.
- Code paths named above predate [ADR-0015](0015-services-layout-high-cohesion-low-coupling.md): `application/authz/policy.py` is now `services/loan-api/src/authz/policy.py`.
