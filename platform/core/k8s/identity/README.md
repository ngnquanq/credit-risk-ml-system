# Identity (E11)

Keycloak with two realms ([ADR-0012](../../../../docs/adr/0012-keycloak-realms-and-bff-portals.md)):

| Realm | Who | Sign-in rules | Roles |
|---|---|---|---|
| `staff` | Lender employees | No self-registration, TOTP enrolled at first sign-in, password policy, brute-force protection | `loan_officer`, `underwriter`, `risk_manager`, `auditor`, `admin`; user attribute `branch_id` |
| `customers` | Applicants | Self-registration with a verified email | `applicant` |

Both realms put audience `credit-api` into access tokens (5 minutes). The API trusts exactly these issuers (`APP_OIDC_ISSUERS`).

## Deploy

```bash
make k8s-cnpg-operator      # once per cluster
make k8s-identity           # needs the Identity variables from .env.example
```

Realm files contain no secrets: client secrets are `${...}` placeholders filled from the `keycloak-clients` Secret at import.

## To verify on the first deployment (not yet run on a cluster)

- Placeholder substitution in the realm import (`${STAFF_PORTAL_CLIENT_SECRET}`, `${SMTP_HOST}`). Set `SMTP_HOST` and `SMTP_PORT` on the StatefulSet, or point them at a local mail catcher for UAT.
- The `mfa` ACR: the staff realm maps `mfa` to level of authentication 2, and the staff client requests it by default. Confirm that staff access tokens carry `"acr": "mfa"` after a TOTP sign-in; the API rejects staff tokens without it (`APP_OIDC_STAFF_REQUIRED_ACR`). If the browser flow does not raise the level, add a "Condition - Level of Authentication" step for level 2 with the OTP form.
- `defaultRoles` in `customers.json`: on Keycloak 26 the default role is the composite `default-roles-customers`. Confirm that new users get `applicant`.
- Test users per role for UAT are created by `scripts/uat/create_test_users.sh` (E16), with generated passwords stored in a Secret.
