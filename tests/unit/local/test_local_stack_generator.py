"""The local UI stack generator (scripts/local/generate.py).

It must produce realms that work on localhost, keep production rules intact in the committed
realm files, line up with the seeded demo data, and never write secrets into tracked files.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "scripts" / "local" / "initdb" / "03-demo-data.sql"
COMMITTED_REALMS = ROOT / "platform" / "core" / "k8s" / "identity" / "realms"


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("local_generate", ROOT / "scripts" / "local" / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def generated(generator, tmp_path):
    out, portals = tmp_path / "generated", tmp_path / "apps"
    generator.generate(out, portals)
    return out, portals


def _realm(out, name):
    return json.loads((out / "realms" / f"{name}.json").read_text())


def _client(realm, client_id):
    return next(c for c in realm["clients"] if c["clientId"] == client_id)


def test_portal_clients_redirect_to_localhost_only(generated):
    out, _ = generated
    staff = _client(_realm(out, "staff"), "staff-portal")
    applicant = _client(_realm(out, "customers"), "applicant-portal")
    assert staff["redirectUris"] == ["http://localhost:3002/auth/callback"]
    assert applicant["redirectUris"] == ["http://localhost:3001/auth/callback"]
    assert "${" not in staff["secret"] and len(staff["secret"]) >= 24


def test_local_relaxations_do_not_touch_the_committed_realms(generated):
    out, _ = generated
    local_totp = next(a for a in _realm(out, "staff")["requiredActions"] if a["alias"] == "CONFIGURE_TOTP")
    assert local_totp["defaultAction"] is False

    committed = json.loads((COMMITTED_REALMS / "staff.json").read_text())
    assert next(a for a in committed["requiredActions"] if a["alias"] == "CONFIGURE_TOTP")["defaultAction"] is True
    assert _client(committed, "staff-portal")["attributes"]["minimum.acr.value"] == "mfa"
    assert committed["users"] == []
    assert _client(committed, "staff-portal")["secret"].startswith("${")


def test_demo_users_match_the_seeded_owners(generated):
    out, _ = generated
    seeded = set(re.findall(r"[12]{8}-[12]{4}-4[12]{3}-8[12]{3}-0{11}\d", SEED.read_text()))
    users = {u["id"] for u in _realm(out, "staff")["users"]} | {u["id"] for u in _realm(out, "customers")["users"]}
    assert seeded and seeded <= users


def test_each_staff_role_has_a_demo_user_and_officers_have_branches(generated):
    out, _ = generated
    staff_users = _realm(out, "staff")["users"]
    roles = {u["realmRoles"][0] for u in staff_users}
    assert roles == {"loan_officer", "underwriter", "risk_manager", "auditor"}
    for user in staff_users:
        if user["realmRoles"] == ["loan_officer"]:
            assert user["attributes"]["branch_id"][0] in {"HN01", "HCM02"}


def test_passwords_are_unique_and_only_in_git_ignored_files(generated):
    out, portals = generated
    passwords = [u["credentials"][0]["value"] for r in ("staff", "customers") for u in _realm(out, r)["users"]]
    assert len(set(passwords)) == len(passwords)
    credentials = (out / "credentials.txt").read_text()
    assert all(p in credentials for p in passwords)
    # Portals get client secrets but never user passwords.
    for app in ("staff-portal", "applicant-portal"):
        env = (portals / app / ".env.local").read_text()
        assert "OIDC_ALLOW_INSECURE_HTTP=true" in env
        assert not any(p in env for p in passwords)


def test_api_env_trusts_both_local_realms(generated):
    out, _ = generated
    env = dict(line.split("=", 1) for line in (out / "api.env").read_text().splitlines() if "=" in line)
    assert env["APP_OIDC_ISSUERS"] == "http://localhost:8180/realms/staff,http://localhost:8180/realms/customers"
    assert env["APP_OIDC_STAFF_REQUIRED_ACR"] == ""
    assert env["APP_AUDIT_DATABASE_URL"].endswith("/audit")


def test_generated_folder_and_portal_env_files_are_git_ignored():
    import subprocess

    for path in ("scripts/local/.generated/credentials.txt", "portals/apps/staff-portal/.env.local"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0, path


def _api_env(out):
    return dict(line.split("=", 1) for line in (out / "api.env").read_text().splitlines() if "=" in line)


def test_demo_identities_are_encrypted_with_the_api_keys(generated):
    """ADR-0014: the seed holds ciphertext only, and the API's keys decrypt it."""
    from identity import PiiCipher

    out, _ = generated
    seed = (out / "seed" / "demo-identity.sql").read_text()
    assert "001091000002" not in seed and "Lý Văn Đức" not in seed and "0901000002" not in seed
    env = _api_env(out)
    cipher = PiiCipher.from_settings(env["APP_PII_KEKS"], env["APP_PII_HMAC_KEY"])
    assert cipher.citizen_id_hmac("001091000002") in seed
    token = re.search(r"'(v1\.local1\.[^']+)'", seed).group(1)
    assert cipher.decrypt("full_name", token) == "Lý Văn Đức"


def test_every_seeded_application_has_an_identity_and_a_public_id(generator):
    rows = re.findall(r"\('(\d{6})', '([0-9a-f-]{36})', '\d{4}-", SEED.read_text())
    assert {ref for ref, _ in rows} == set(generator.DEMO_IDENTITIES)
    assert len({pid for _, pid in rows}) == len(rows)


def test_document_store_is_local_and_only_the_portals_get_its_origin(generated):
    out, portals = generated
    env = _api_env(out)
    assert env["MINIO_ENDPOINT"] == "localhost:9000" and env["APP_MINIO_PUBLIC_URL"] == "http://localhost:9000"
    minio = (out / "minio.env").read_text()
    for app in ("staff-portal", "applicant-portal"):
        portal_env = (portals / app / ".env.local").read_text()
        assert "STORAGE_PUBLIC_ORIGIN=http://localhost:9000" in portal_env
        assert minio.split("MINIO_ROOT_PASSWORD=")[1].strip() not in portal_env
