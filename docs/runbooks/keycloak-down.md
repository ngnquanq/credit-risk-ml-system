# Keycloak down

**Notice.** Sign-in errors in both portals; `/health/ready` failing on `keycloak-*` pods.

**What already happens.** With one replica down, the other serves. With both down, existing sessions keep working until the access token needs refreshing (at most 5 minutes). After that, users are sent to a sign-in page that fails. The API rejects nothing it would otherwise accept: it only needs the cached signing keys.

**Do.**
1. `kubectl get pods -n identity`. Check `keycloak-db` (CloudNativePG) first: Keycloak cannot start without its database.
2. Restart Keycloak pods one at a time (`kubectl delete pod keycloak-0 -n identity`) to keep one serving.
3. Do not re-import realms on a running cluster. Realm changes go through git and a planned redeploy.

**Confirm.** A staff sign-in with TOTP works; staff access tokens carry `acr=mfa`; applicant sign-in works.
