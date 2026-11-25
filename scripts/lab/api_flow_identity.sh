#!/usr/bin/env bash
# LAB ONLY. Prepare a lab cluster so scripts/e2e/api_flow.py can call the Loan API as an applicant.
#   up    self-signed certificate for the auth host, the API trusts it and resolves the host, a test applicant,
#         password grant on the portal client, and an access token written to $TOKEN_FILE (mode 600)
#   down  password grant off again, token file removed
# Needs kubectl, openssl, python3 and these in the environment: APPLICANT_PORTAL_CLIENT_SECRET.
# The applicant's password is generated into ~/crs-lab-user.env the first time. Nothing secret is printed.
set -euo pipefail

AUTH_HOST="${AUTH_HOST:-auth.credit.local}"
TOKEN_FILE="${TOKEN_FILE:-/tmp/crs-token}"
USER_ENV="${USER_ENV:-$HOME/crs-lab-user.env}"
EMAIL="lab-applicant@example.test"
kc() { kubectl exec -i -n identity keycloak-0 -- env "${@:2}" bash -s <<<"$1"; }
KCADM='K=/opt/keycloak/bin/kcadm.sh; $K config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null 2>&1;'
client_id='CID=$($K get clients -r customers -q clientId=applicant-portal --fields id --format csv --noquotes);'

up() {
  local jwks_url pod attempt
  umask 077
  [ -f "$USER_ENV" ] || python3 -c "import secrets; print('export LAB_APPLICANT_PASSWORD=' + secrets.token_urlsafe(18))" > "$USER_ENV"
  set -a; . "$USER_ENV"; set +a

  # 1. TLS for the auth host: the API fetches signing keys from https://$AUTH_HOST/...
  dir="$(mktemp -d)"; trap 'rm -rf "$dir"' RETURN
  if ! kubectl get secret auth-tls -n identity -o jsonpath='{.data.tls\.crt}' | openssl base64 -d -A > "$dir/crt" ||
     ! openssl x509 -in "$dir/crt" -noout -checkend 86400 >/dev/null 2>&1 ||
     ! openssl verify -CAfile "$dir/crt" -verify_hostname "$AUTH_HOST" "$dir/crt" >/dev/null 2>&1; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 30 -keyout "$dir/key" -out "$dir/crt" -subj "/CN=$AUTH_HOST" -addext "subjectAltName=DNS:$AUTH_HOST" 2>/dev/null
    kubectl create secret tls auth-tls -n identity --cert="$dir/crt" --key="$dir/key" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  fi
  kubectl create secret generic auth-ca -n api-gateway --from-file=ca.crt="$dir/crt" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  kubectl patch ingress keycloak -n identity --type=json -p "[{\"op\":\"add\",\"path\":\"/spec/tls\",\"value\":[{\"hosts\":[\"$AUTH_HOST\"],\"secretName\":\"auth-tls\"}]}]" >/dev/null
  ip="$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.spec.clusterIP}')"
  kubectl patch deployment api-service -n api-gateway --patch "$(cat <<YAML
spec:
  template:
    spec:
      hostAliases: [{ip: "$ip", hostnames: ["$AUTH_HOST"]}]
      volumes: [{name: auth-ca, secret: {secretName: auth-ca}}]
      containers:
        - name: api
          env: [{name: SSL_CERT_FILE, value: /etc/auth-ca/ca.crt}]
          volumeMounts: [{name: auth-ca, mountPath: /etc/auth-ca, readOnly: true}]
YAML
)" >/dev/null
  kubectl rollout status deployment/api-service -n api-gateway --timeout=240s >/dev/null
  # Pod readiness checks /health. Wait for the ingress and each API pod to agree on the new TLS cert too.
  jwks_url="https://$AUTH_HOST/realms/customers/protocol/openid-connect/certs"
  for pod in $(kubectl get pods -n api-gateway -l app=api-service --field-selector=status.phase=Running -o name); do
    for attempt in {1..45}; do
      if kubectl exec -n api-gateway "$pod" -- python -c \
        'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=4).close()' "$jwks_url" >/dev/null 2>&1; then
        break
      fi
      if [ "$attempt" -eq 45 ]; then
        echo "$pod could not fetch the Keycloak signing keys over TLS" >&2
        return 1
      fi
      sleep 2
    done
  done

  # 2. A test applicant (the realm uses the email as the username) and the password grant on the portal client
  kc "$KCADM"'
    UID_=$($K get users -r customers -q email='"$EMAIL"' --fields id --format csv --noquotes)
    if [ -z "$UID_" ]; then $K create users -r customers -s username='"$EMAIL"' -s email='"$EMAIL"' -s enabled=true -s emailVerified=true -s firstName=Lab -s lastName=Applicant >/dev/null; UID_=$($K get users -r customers -q email='"$EMAIL"' --fields id --format csv --noquotes); fi
    $K set-password -r customers --userid "$UID_" --new-password "$APPLICANT_PW"
    $K add-roles -r customers --uid "$UID_" --rolename applicant
    '"$client_id"' $K update clients/$CID -r customers -s directAccessGrantsEnabled=true' APPLICANT_PW="$LAB_APPLICANT_PASSWORD"

  # 3. Token (through a short-lived port-forward)
  kubectl port-forward -n identity svc/keycloak 18080:8080 >/dev/null 2>&1 & pf=$!; trap 'kill $pf 2>/dev/null; rm -rf "$dir"' RETURN; sleep 3
  python3 - "$EMAIL" "$TOKEN_FILE" <<'PY'
import json, os, sys, urllib.parse, urllib.request
email, out = sys.argv[1:3]
data = urllib.parse.urlencode({"grant_type": "password", "client_id": "applicant-portal", "client_secret": os.environ["APPLICANT_PORTAL_CLIENT_SECRET"],
                               "username": email, "password": os.environ["LAB_APPLICANT_PASSWORD"]}).encode()
token = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18080/realms/customers/protocol/openid-connect/token", data=data), timeout=20))["access_token"]
open(out, "w").write(token); os.chmod(out, 0o600)
PY
  echo "ready: token in $TOKEN_FILE. Run scripts/e2e/api_flow.py with TOKEN=\$(cat $TOKEN_FILE); then: $0 down"
}

down() {
  kc "$KCADM $client_id"' $K update clients/$CID -r customers -s directAccessGrantsEnabled=false'
  rm -f "$TOKEN_FILE"; echo "password grant off, token removed"
}

case "${1:-}" in up) up ;; down) down ;; *) echo "usage: $0 up|down" >&2; exit 2 ;; esac
