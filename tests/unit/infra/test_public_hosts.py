"""Public host names are defined once (platform/config/public-hosts/hosts.env) and every environment changes them together."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
HOSTS = {
    k: v for k, _, v in (l.partition("=") for l in (ROOT / "platform/config/public-hosts/hosts.env").read_text().splitlines()
                         if l.strip() and not l.startswith("#"))
}
PODS = ["portals/deploy/portals.yaml", "platform/foundation/identity/02-keycloak.yaml", "services/loan-api/deploy/api/05-api.yaml"]


def _ingress_hosts(path: str) -> dict[str, str]:
    out = {}
    for doc in yaml.safe_load_all((ROOT / path).read_text()):
        if doc and doc.get("kind") == "Ingress":
            out[doc["metadata"]["name"]] = doc["spec"]["rules"][0]["host"]
    return out


def test_base_ingress_hosts_match_the_defaults():
    hosts = {**_ingress_hosts("portals/deploy/portals.yaml"), **_ingress_hosts("platform/foundation/identity/02-keycloak.yaml")}
    assert hosts == {"applicant-portal": HOSTS["APPLY_HOST"], "staff-portal": HOSTS["STAFF_HOST"], "keycloak": HOSTS["AUTH_HOST"]}


def test_pod_specs_do_not_write_a_public_host_out():
    for path in PODS:
        text = re.sub(r"(?m)^\s*- host: .*$", "", (ROOT / path).read_text())  # ingress hosts are replaced per environment
        for key, host in HOSTS.items():
            assert host not in text, f"{path} writes {host} out; read {key} from the public-hosts ConfigMap"


def test_realm_files_use_placeholders_for_the_portal_hosts():
    for realm, key in (("customers", "APPLY_HOST"), ("staff", "STAFF_HOST")):
        text = (ROOT / f"platform/foundation/identity/realms/{realm}.json").read_text()
        json.loads(text)
        assert HOSTS[key] not in text and "${" + key + "}" in text


def test_every_overlay_that_changes_hosts_changes_all_of_them():
    for env in ("uat",):
        text = (ROOT / f"platform/environments/{env}/kustomization.yaml").read_text()
        for key in HOSTS:
            assert f"/data/{key}" in text, f"the {env} overlay does not set {key}"
