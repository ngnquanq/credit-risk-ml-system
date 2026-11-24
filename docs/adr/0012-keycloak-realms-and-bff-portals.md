# ADR-0012: Keycloak with two realms, and backend-for-frontend portals

## Status

Accepted

## Date

2026-11-22

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
