# Scripts

Everything here is for development, a lab cluster or a developer's laptop. **None of it ships to production.**

| Folder | Purpose |
|---|---|
| `local/` | Run the stack on one machine (compose, seed data) |
| `e2e/` | End-to-end checks against a running API (`api_flow.py`: applicant flow with documents) |
| `lab/` | Set up a throwaway lab cluster for those checks (self-signed certificate, a test user, a token) |
| `parity/` | Compare feature code paths on a running cluster (`make k8s-parity-bureau`) |
| `chaos/`, `uat/` | Failure and acceptance drills |

The root `.dockerignore` excludes `scripts/` from every image built from the repository root, and
`tests/unit/infra/test_dev_scripts_not_shipped.py` fails if a Dockerfile copies from here or the exclusion is removed.
