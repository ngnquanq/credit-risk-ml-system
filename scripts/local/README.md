# Local UI stack

Try both portals on your machine with real sign-in, the real API and permission checks, and demo data. No Kafka, Flink, Feast or model: decisions are pre-seeded.

| Piece | Where | How |
|---|---|---|
| Keycloak (realms `staff`, `customers`, demo users) | http://localhost:8180 | Docker |
| PostgreSQL (`operations` with demo data, `audit`) | localhost:5433 | Docker |
| Redis (portal sessions, estimator drafts) | localhost:6380 | Docker |
| MinIO (applicant documents, 90-day expiry) | http://localhost:9000 (console :9001) | Docker |
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
| E2E, 29 journeys | `cd portals && pnpm e2e:local` | Officer (incl. walk-in entry with ID photo, masked ID and audited reveal), underwriter, risk managers, auditor; applicant on desktop and iPhone 14 size (estimator → apply with uploads, no data in URLs, no sideways scroll). Adds an iPhone/WebKit run when `npx playwright install webkit` was done. Resets demo data first (`reset_demo.sh`); uses the installed Chrome |
| Audit on real PostgreSQL | `pytest tests/integration/audit` | Writer, reader, hash chain verified by `audit.verify_job` (skips when the stack is down) |
| Generator | `pytest tests/unit/local` | Localhost-only redirects, demo users match the seed, passwords only in git-ignored files, committed realms keep MFA, demo identities encrypted with the API's keys |
| Portal security | `cd portals/packages/auth && pnpm test` | http issuer never allowed in production, CSP nonce per request, `unsafe-eval` only in dev, sign-in redirect |

## Demo users

Usernames and generated passwords are in `scripts/local/.generated/credentials.txt` (git-ignored; `python scripts/local/generate.py --force` rotates them).

Applications are addressed by opaque ids (ADR-0014); the seeded ones are fixed so they can be bookmarked:

| Ref | Id | Case |
|---|---|---|
| HS-F0155E69 | `f0155e69-6681-49e9-86c0-6c92e99d27c9` | HN01, manual review with model reasons (customer Lý Văn Đức) |
| HS-660D6FD8 | `660d6fd8-0cb9-4aa2-b279-cfc342be4e9e` | HN01, approved |
| HS-425478CC | `425478cc-e1e9-4da2-a7f3-bf22ff734e3c` | HCM02, manual review, features incomplete |
| HS-A1202DFB | `a1202dfb-1bf4-4942-9894-2523ea299667` | entered by the underwriter (separation of duties) |
| HS-4619A4EB | `4619a4eb-f94f-4fb9-ad3f-c28bb366caf6` | applicant A, rejected with reasons |
| HS-88D3098B | `88d3098b-e09e-42c6-a814-0259cc0185f7` | applicant B, approved |

| User | Role | Try |
|---|---|---|
| `officer.hn01` | loan officer, HN01 | `/cases/f0155e69-…` (masked ID; "Show citizen ID and phone" asks for a reason); `/cases/425478cc-…` is another branch and is refused; `/applications/new` with an ID photo |
| `officer.hcm02` | loan officer, HCM02 | the mirror image |
| `underwriter` | underwriter | `/reviews`: HS-F0155E69 (with contributions), HS-425478CC (features incomplete), HS-A1202DFB marked "You submitted this one" |
| `risk.manager1`, `risk.manager2` | risk managers | propose bands as one, approve as the other (four eyes) |
| `auditor` | auditor | `/audit?id=f0155e69-6681-49e9-86c0-6c92e99d27c9` after the others have clicked around: the reveal is there with its reason, the numbers are not |
| `applicant.a@demo.local` | applicant | `/applications` (my applications), then HS-4619A4EB (rejected, reasons in Vietnamese); applicant B's id shows "not found" |
| `applicant.b@demo.local` | applicant | home page → "Bắt đầu hồ sơ" → `/apply` (no query string) with ID photos |

Coming from an older local stack: `make local-ui-down && python scripts/local/generate.py --force && make local-ui-up` (new schema, keys and MinIO; demo passwords rotate).

## Local-only relaxations

These exist only in the generated files, never in the committed realms or manifests:
- staff TOTP is not forced, and the API's `acr=mfa` check is off (`APP_OIDC_STAFF_REQUIRED_ACR=`);
- issuers are plain http (`OIDC_ALLOW_INSECURE_HTTP=true`, ignored in production builds);
- email verification is off for new applicant registrations (no mail server).

The customer profile panel stays empty locally (no ClickHouse: it fails fast with 503 and never holds up other requests); submissions are stored but not scored (no Kafka or model).
