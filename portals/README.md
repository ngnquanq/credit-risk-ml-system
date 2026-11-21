# Portals (E12)

Two Next.js (App Router, TypeScript) backends-for-frontend ([ADR-0012](../docs/adr/0012-keycloak-realms-and-bff-portals.md)):

| App | Host | Realm | Users |
|---|---|---|---|
| `apps/applicant-portal` | `apply.credit.local` (public ingress, rate-limited) | `customers` | Applicants (Vietnamese UI, phone-first, desktop too) |
| `apps/staff-portal` | `staff.credit.local` (internal ingress) | `staff` | Loan officers, underwriters, risk managers, auditors |

Shared packages:
- `packages/auth`: OIDC authorization code + PKCE, a Redis session store, CSRF and Origin checks, role guards. Tokens stay on the server; the browser only holds the `__Host-session` cookie.
- `packages/api`: typed calls to the Loan API with the user's access token (token relay). `pnpm generate:api` regenerates types from `contracts/openapi/loan-api.json`.
- `packages/ui`: palette (red `#C8102E`, black, greys, white) and small components.

The API is the authority on permissions (E11). The portals hide what a role cannot do, but every call is still checked by the API.

## Run locally

```bash
pnpm install
cp apps/applicant-portal/.env.example apps/applicant-portal/.env.local   # fill in values
pnpm dev:applicant
```

## Status (2026-11-22)

Written, not yet installed, type-checked or run. First steps: `pnpm install`, `pnpm generate:api`, `pnpm typecheck`, then the Playwright specs under `apps/*/e2e/` against UAT.
