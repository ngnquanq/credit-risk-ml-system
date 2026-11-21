#!/usr/bin/env bash
# Creates one UAT test user per role (E16) in the staff and customers realms via the Keycloak
# admin API. Passwords are generated here and stored only in the Kubernetes Secret uat-test-users;
# nothing is printed or written to the repository. Staff users must enrol TOTP at first sign-in.
#
#   KEYCLOAK_URL=https://auth.credit.local KEYCLOAK_ADMIN_PASSWORD=... scripts/uat/create_test_users.sh
set -euo pipefail

KC="${KEYCLOAK_URL:?set KEYCLOAK_URL}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:?set KEYCLOAK_ADMIN_PASSWORD}"
NAMESPACE="${UAT_NAMESPACE:-identity}"

token=$(curl -fsS -X POST "$KC/realms/master/protocol/openid-connect/token" \
  --data-urlencode grant_type=password --data-urlencode client_id=admin-cli \
  --data-urlencode username=admin --data-urlencode "password=$ADMIN_PASSWORD" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

secret_args=()

create_user() {  # realm username role [branch]
  local realm="$1" username="$2" role="$3" branch="${4:-}"
  local password
  password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  local attrs="{}"
  [[ -n "$branch" ]] && attrs="{\"branch_id\": [\"$branch\"]}"
  curl -fsS -X POST "$KC/admin/realms/$realm/users" -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    -d "{\"username\": \"$username\", \"email\": \"$username@uat.credit.local\", \"enabled\": true, \"emailVerified\": true,
         \"attributes\": $attrs,
         \"credentials\": [{\"type\": \"password\", \"value\": \"$password\", \"temporary\": false}]}" >/dev/null || true
  local user_id role_json
  user_id=$(curl -fsS "$KC/admin/realms/$realm/users?username=$username&exact=true" -H "Authorization: Bearer $token" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
  role_json=$(curl -fsS "$KC/admin/realms/$realm/roles/$role" -H "Authorization: Bearer $token")
  curl -fsS -X POST "$KC/admin/realms/$realm/users/$user_id/role-mappings/realm" -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" -d "[$role_json]" >/dev/null
  secret_args+=("--from-literal=$username=$password")
  echo "created $realm/$username ($role${branch:+, branch $branch})"
}

create_user staff uat-officer-hn01 loan_officer HN01
create_user staff uat-officer-hcm02 loan_officer HCM02
create_user staff uat-underwriter-1 underwriter
create_user staff uat-underwriter-2 underwriter
create_user staff uat-risk-1 risk_manager
create_user staff uat-risk-2 risk_manager
create_user staff uat-auditor auditor
create_user customers uat-applicant-a applicant
create_user customers uat-applicant-b applicant

kubectl create secret generic uat-test-users -n "$NAMESPACE" "${secret_args[@]}" --dry-run=client -o yaml | kubectl apply -f -
echo "Passwords stored in secret $NAMESPACE/uat-test-users"
