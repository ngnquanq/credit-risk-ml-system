# Local UI stack

Try both portals on your machine with real sign-in, the real API and permission checks, and demo data. No Kafka, Flink, Feast or model: decisions are pre-seeded.

| Piece | Where | How |
|---|---|---|
| Keycloak (realms `staff`, `customers`, demo users) | http://localhost:8180 | Docker |
| PostgreSQL (`operations` with demo data, `audit`) | localhost:5433 | Docker |
| Redis (portal sessions) | localhost:6380 | Docker |
| Loan API | http://localhost:8000 | `make local-api` (your Python env with `application/requirements-api.txt`) |
| Staff portal | http://localhost:3002 | `cd portals && pnpm dev:staff` |
| Applicant portal | http://localhost:3001 | `cd portals && pnpm dev:applicant` |

```bash
make local-ui-up        # generates secrets, starts Docker services (first start pulls images)
make local-api          # terminal 1
cd portals && pnpm dev:staff        # terminal 2
cd portals && pnpm dev:applicant    # terminal 3
make local-ui-down      # stop and wipe
```

Use Chrome: the session cookie is `__Host-` and `Secure`, which browsers accept on `http://localhost`.

## Tests on this stack

| Suite | Command | What it covers |
|---|---|---|
| E2E, 19 journeys | `cd portals && pnpm e2e:local` | Officer, underwriter, risk managers, auditor (staff portal); applicant on desktop and phone. Resets demo data first (`reset_demo.sh`); uses the installed Chrome |
| Audit on real PostgreSQL | `pytest tests/integration/audit` | Writer, reader, hash chain verified by `audit.verify_job` (skips when the stack is down) |
| Generator | `pytest tests/unit/local` | Localhost-only redirects, demo users match the seed, passwords only in git-ignored files, committed realms keep MFA |
| Portal security | `cd portals/packages/auth && pnpm test` | http issuer never allowed in production, CSP nonce per request, `unsafe-eval` only in dev, sign-in redirect |

## Demo users

Usernames and generated passwords are in `scripts/local/.generated/credentials.txt` (git-ignored; `python scripts/local/generate.py --force` rotates them).

| User | Role | Try |
|---|---|---|
| `officer.hn01` | loan officer, HN01 | `/cases/100002` (internal factors, reasons, no score); `/cases/100561` is another branch and is refused; new application |
| `officer.hcm02` | loan officer, HCM02 | the mirror image |
| `underwriter` | underwriter | `/reviews`: 100002 (with contributions), 100561 (features incomplete), 100600 marked "You submitted this one" |
| `risk.manager1`, `risk.manager2` | risk managers | propose bands as one, approve as the other (four eyes) |
| `auditor` | auditor | `/audit?id=100002` after the others have clicked around |
| `applicant.a@demo.local` | applicant | `/applications/100417` (rejected, reasons in Vietnamese); `/applications/100700` belongs to B and shows "not found" |
| `applicant.b@demo.local` | applicant | `/applications/100700` |

## Local-only relaxations

These exist only in the generated files, never in the committed realms or manifests:
- staff TOTP is not forced, and the API's `acr=mfa` check is off (`APP_OIDC_STAFF_REQUIRED_ACR=`);
- issuers are plain http (`OIDC_ALLOW_INSECURE_HTTP=true`, ignored in production builds);
- email verification is off for new applicant registrations (no mail server).

The customer profile panel stays empty locally (no ClickHouse); submissions are stored but not scored (no Kafka or model).
