# E12: Staff and applicant portals

| Epic | Outcome / KPI | Baseline → target | Size | Depends on |
|---|---|---|---|---|
| [E12 Portals](../02-product/epics.md#e12-staff-and-applicant-portals) | [O1](../01-business/business-outcomes.md#o1-applicants-get-an-answer-fast) fast decision; [O7](../01-business/business-outcomes.md#o7-applicant-data-is-protected) data protection; [O8](../01-business/business-outcomes.md#o8-decisions-are-explainable-and-accountable) explainable decisions | One unauthenticated Streamlit form, no decision shown → two signed-in portals; every role sees its decision, queue or trace; no token reachable from browser JavaScript | L | [E11 Identity and access](../02-product/epics.md#e11-identity-and-access) (identity), [E5](../02-product/epics.md#e5-decision-delivery-and-status-tracking) (decisions), [E14](../02-product/epics.md#e14-explainability) (reasons), [E13](../02-product/epics.md#e13-audit-trail) (audit trace) |

## 1. Why

- **Nothing to read back.** The Streamlit form submits and stops. Nobody sees the decision.
- **One screen for everyone.** Staff and applicants share it, so the UI cannot show different data or actions per role.
- **Unfit for hardening.** A Python server-rendered app cannot easily carry a BFF session model, CSP and per-role routing.

## 2. Scope

**In**
- **Two Next.js (App Router, TypeScript) apps in one workspace** under `portals/`:
  - `staff-portal` on host `staff.credit.local`, behind the internal ingress.
  - `applicant-portal` on host `apply.credit.local`, behind the public ingress with rate limits.
  - Shared package `portals/packages/api-client`, generated from the API's OpenAPI schema, with shared UI primitives.
- **BFF session.** Sign-in with the authorization code flow + PKCE. Tokens are stored server side, keyed by an opaque session id. The browser holds one cookie: `__Host-session`, `HttpOnly`, `Secure`, `SameSite=Lax`.
  - Refresh happens server side.
  - Logout revokes the refresh token and clears the session.
- **Mutation protection.** Server actions or route handlers only. Every mutation checks a CSRF token bound to the session, plus the `Origin` header.
- **Security headers:** strict CSP (no inline script without a nonce), `frame-ancestors 'none'`, HSTS, `Referrer-Policy: no-referrer`, `Permissions-Policy`.
- **Screens.**

| Portal | Role | Screens |
|---|---|---|
| applicant | applicant | Register / sign in (Keycloak pages), Apply (multi-step form with document upload), My applications, Application detail (status timeline, decision, principal reasons) |
| staff | loan_officer | New application (for a walk-in customer), Branch applications, Case view: internal factors for the customer they serve, reasons the customer sees, documents to collect, note and flag actions, customer lookup by ID with purpose. No approve or reject, no score ([ADR-0013](../adr/0013-role-based-data-and-explanation-visibility.md)) |
| staff | underwriter | Review queue (oldest first), Claim, Case in three steps: evidence, then model explanation, then decision (approve or reject with reason code and mandatory text) |
| staff | risk_manager | Policy (current bands), Propose change, Pending approvals |
| staff | auditor | Decision trace (by application id): timeline of audit events with hash-chain status |

- **Layouts and look:** every applicant screen exists at phone width (390 px, the primary channel) and desktop width (≥1280 px); staff screens are desktop-first and still usable on a tablet. Palette: red `#C8102E` for primary actions and risk-raising contributions, black `#111111` text, greys `#3F3F46`/`#52525B` for secondary text, `#E4E4E7`/`#F4F4F5` for borders and grounds, white surfaces. All text pairs meet 4.5:1. Fonts: Be Vietnam Pro (applicant, Vietnamese copy), Inter (staff, English).
- **Removal:** The Streamlit source and manifests have been removed from the repository.

**Out**
- Native mobile apps, notifications (email or SMS), internationalisation beyond English and Vietnamese labels.

## 3. Original baseline

As-built view: [`L2-1-Intake`](../architecture/c4/docs/images/L2-1-Intake.svg). Streamlit calls the API from its pod; no sign-in; no read-back.

## 4. Target design

### 4.1 C4

[`T-E12-Portals`](../architecture/c4/docs/images/T-E12-Portals.svg):

![T-E12-Portals](../architecture/c4/docs/images/T-E12-Portals.svg)

Applicant flow [`T-D12-Applicant-Self-Service`](../architecture/c4/docs/images/T-D12-Applicant-Self-Service.svg):

![T-D12-Applicant-Self-Service](../architecture/c4/docs/images/T-D12-Applicant-Self-Service.svg)

### 4.2 Module interface (UML)

```mermaid
classDiagram
    direction LR
    class SessionStore {
        <<portals/packages/session>>
        +create(tokens, user) SessionId
        +get(id) Session or None
        +refreshIfNeeded(id) Session
        +destroy(id) None
    }
    class Session {
        +sub: string
        +roles: string[]
        +branchId: string or null
        +accessToken: string
        +refreshToken: string
        +expiresAt: number
        +csrfToken: string
    }
    class OidcClient {
        <<openid-client>>
        +authorizationUrl(state, codeVerifier) URL
        +callback(params, checks) TokenSet
        +refresh(refreshToken) TokenSet
        +revoke(token) void
    }
    class ApiClient {
        <<portals/packages/api-client, generated>>
        +submitApplication(body) Application
        +getDecision(id) Decision
        +listReviews() Review[]
        +decideReview(id, decision, reason) void
        +getAuditTrace(id) AuditEvent[]
    }
    class RoleGuard {
        <<middleware.ts>>
        +require(roles) Response or next
    }
    SessionStore ..> Session
    SessionStore ..> OidcClient : refresh
    ApiClient ..> SessionStore : bearer from session
    RoleGuard ..> SessionStore
```

Sessions are stored in Redis (namespace `portals`, its own instance, 30-minute idle timeout, 8-hour absolute timeout). The role guard only shapes navigation; **the API remains the authority** ([E11 Identity and access](../02-product/epics.md#e11-identity-and-access)). A screen hidden by the guard must still be rejected by the API.

### 4.3 Behaviour

Sign-in and a mutation in the staff portal:

```mermaid
sequenceDiagram
    autonumber
    actor U as Underwriter (browser)
    participant SP as Staff portal (Next.js)
    participant KC as Keycloak (staff realm)
    participant RS as Session store (Redis)
    participant API as Loan API
    U->>SP: GET /reviews
    SP-->>U: 302 to Keycloak (state, PKCE challenge)
    U->>KC: password + TOTP
    KC-->>U: 302 /auth/callback?code
    U->>SP: GET /auth/callback?code&state
    SP->>KC: exchange code + verifier (client secret)
    KC-->>SP: access, refresh, id tokens
    SP->>RS: create session
    SP-->>U: Set-Cookie __Host-session (HttpOnly), page with CSRF token
    U->>SP: POST /reviews/123/decision (CSRF token, Origin)
    SP->>SP: check CSRF + Origin, refresh token if near expiry
    SP->>API: POST /api/v1/reviews/123/decision, Bearer access token
    API-->>SP: 204 (or 403 with rule)
    SP-->>U: updated queue
```

Applicant status polling: the detail page polls `GET /api/v1/applications/{id}/decision` every 2 s for up to 60 s, then every 15 s. Server-sent events can replace polling later.

## 5. Data contracts

**Decision as shown to an applicant** (`GET /api/v1/applications/{id}/decision`, owner only)

```json
{
  "application_id": "f0155e69-6681-49e9-86c0-6c92e99d27c9",
  "status": "manual_review",
  "amt_credit": 40000000,
  "submitted_at": "2026-12-02T09:12:40Z",
  "decided_at": "2026-12-02T09:14:03Z",
  "reasons": [
    {"code": "EXT_SCORE_LOW", "text": "Điểm tín dụng từ nguồn bên ngoài thấp"},
    {"code": "CREDIT_TO_GOODS_HIGH", "text": "Số tiền vay cao so với giá trị hàng hoá hoặc thu nhập"}
  ],
  "history": [{"status": "submitted", "at": "2026-12-02T09:12:40Z"}, {"status": "manual_review", "at": "2026-12-02T09:14:03Z"}]
}
```

The language of the reasons follows `Accept-Language` (the BFF sends `vi` for applicants, `en` for staff).

**URLs and money** ([ADR-0014](../adr/0014-applicant-personal-data-and-opaque-ids.md))
- Page URLs carry only the opaque application id: `/applications/{public_id}`, `/cases/{public_id}`, `/reviews/{public_id}`.
- People see a short reference, `HS-F0155E69`.
- The estimator posts to a server action that keeps amount and term in a server-side draft (`__Host-draft`, httpOnly, 30 minutes); `/apply` has no query string.
- Amounts are shown and typed as `40,000,000 ₫` (comma every three digits). Money inputs are `type="text" inputMode="numeric"` with live grouping, never `type="number"`.
- Documents go browser → storage with the presigned POST policy from `POST /api/v1/presigned-url`. The CSP `connect-src` lists only `STORAGE_PUBLIC_ORIGIN`.

Applicants never see the raw score, band thresholds or contributions. Staff detail views include score, band, contributions and model version.

**Environment** (per portal)

| Variable | Source |
|---|---|
| `OIDC_ISSUER`, `OIDC_CLIENT_ID` | ConfigMap |
| `OIDC_CLIENT_SECRET`, `SESSION_SECRET` | Secret, created by `make k8s-secrets` |
| `API_BASE_URL` | ConfigMap: `http://api-service.api-gateway.svc` |
| `SESSION_REDIS_URL` | ConfigMap |
| `STORAGE_PUBLIC_ORIGIN` | ConfigMap: origin browsers upload documents to (added to CSP `connect-src`) |

## 6. Change list

| File | Change |
|---|---|
| `portals/` | **new** pnpm workspace: `apps/staff-portal`, `apps/applicant-portal`, `packages/api-client`, `packages/session`, `packages/ui` |
| `contracts/openapi/loan-api.json`, `portals/packages/api-client` | schema exported by `make contracts`; client generated from it (`openapi-typescript`); both checked in, CI regenerates and diffs ([ADR-0011](../adr/0011-monorepo-layout-for-portals-contracts-and-environments.md)) |
| `portals/deploy/` | **new**: Deployments (2 replicas each), Services, Ingresses (public with `limit-rps`, internal with source allow-list), Redis for sessions, NetworkPolicies |
| `services/loan-api/src/entrypoints/api/main.py` | `GET /api/v1/applications/{id}/decision`; CORS no longer needed (calls come from the BFF server) |
| Legacy Streamlit source, Deployment, Service and Ingress | Removed from the repository |
| `Makefile` | `portals-build`, `k8s-portals`; `check` runs `pnpm -r lint test` |

## 7. Acceptance criteria → tests

| # | Given / When / Then | Test |
|---|---|---|
| AC1 | Given any page after sign-in, then no access or refresh token is present in `localStorage`, `sessionStorage`, `document.cookie` or the HTML | Playwright `security.spec.ts` |
| AC2 | Given a POST without the CSRF token or with a foreign `Origin`, then `403` and no API call is made | Playwright + route handler unit test |
| AC3 | Given each role, then its scripted journey passes (applicant applies and reads reasons; officer submits; underwriter claims and decides; risk manager proposes and a second one approves; auditor traces) | Playwright `journeys/*.spec.ts` against UAT |
| AC4 | Given an applicant, when typing another application id into the URL, then the page shows "not found" and the API logged a `403` | Playwright `idor.spec.ts` |
| AC5 | Given response headers, then CSP, HSTS, `frame-ancestors 'none'` and `Referrer-Policy` are present | Playwright `headers.spec.ts`; ZAP baseline ([E16 UAT and release](../02-product/epics.md#e16-uat-and-release-readiness)) |
| AC6 | Given 30 minutes idle, then the next request redirects to sign-in | unit test of `SessionStore` with a fake clock |
| AC7 | Given axe-core, then no serious or critical accessibility violations on the five main screens | Playwright + `@axe-core/playwright` |
| AC8 | Given the estimator → apply → submit journey, then no request URL contains the amount, term, citizen ID or phone | `e2e-local/applicant.spec.ts` |
| AC9 | Given any amount on either portal, then it is grouped with commas; typing `15000000` shows `15,000,000` | `packages/ui/src/format.test.ts`, E2E |
| AC10 | Given an iPhone-sized screen (390 px), then the header stays on one line and no page scrolls sideways, signed in or not | `e2e-local/applicant.spec.ts` (iPhone 14 profile) |
| AC11 | Given a self-service submission without both ID card sides, then the browser stops it, and the API returns `422` if it gets through | E2E; `tests/integration/api/test_personal_data.py` |

## 8. Test plan by layer

| Layer | What |
|---|---|
| Unit (Vitest) | session store, CSRF check, role guard, reason rendering |
| Contract | generated API client compiles against the current OpenAPI schema |
| E2E (Playwright) | one journey per role, security specs, accessibility, against UAT with seeded test users |

## 9. Rollout, rollback, observability

1. Deploy both portals.
2. Run UAT ([E16 UAT and release](../02-product/epics.md#e16-uat-and-release-readiness)).
3. Route the public host to the applicant portal.

**Rollback:** Redeploy the previous portal image. Clusters that still have the retired Streamlit Deployment, Service or Ingress need a separate cleanup.

**Signals:** portal request latency and error rate; sign-in failures; CSP violation reports (`report-to` endpoint logged to ECK).

## 10. Risks and open questions

| Item | Owner | Note |
|---|---|---|
| Node.js is a new runtime to patch and scan | platform | Pin the base image; `npm audit` and trivy in the release checklist |
| Session store availability | platform | Redis outage signs everyone out; acceptable, documented in [E15 Resilience and failover](../02-product/epics.md#e15-resilience-and-failover) |
| Staff network is simulated | architect | An allow-list on the internal ingress stands in for a VPN or zero-trust proxy |
