"""Scripts for local and lab use (scripts/e2e, scripts/lab, scripts/parity, scripts/local) never reach an image."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILES = [p for p in ROOT.rglob("Dockerfile") if not {"node_modules", ".git"} & set(p.parts)
               and "kubeflow" not in p.parts]  # vendored third-party deployer image
COPY = re.compile(r"^\s*(COPY|ADD)\b(?P<args>.*)$", re.IGNORECASE | re.MULTILINE)


def test_the_root_dockerignore_keeps_scripts_and_tests_out_of_every_image():
    entries = {line.strip().rstrip("/") for line in (ROOT / ".dockerignore").read_text().splitlines() if line.strip() and not line.startswith("#")}
    assert {"scripts", "tests"} <= entries


def test_no_dockerfile_copies_from_the_scripts_folder():
    offenders = []
    for dockerfile in DOCKERFILES:
        for match in COPY.finditer(dockerfile.read_text()):
            sources = [t for t in match["args"].split() if not t.startswith("--")][:-1]
            if any(t.lstrip("./").startswith("scripts/") or t.rstrip("/") == "scripts" for t in sources):
                offenders.append(f"{dockerfile.relative_to(ROOT)}: {match.group(0).strip()}")
    assert offenders == [], offenders


def test_the_dev_script_folders_exist_and_are_described():
    readme = (ROOT / "scripts" / "README.md").read_text()
    for folder in ("e2e", "lab", "parity", "local"):
        assert (ROOT / "scripts" / folder).is_dir() and f"`{folder}/`" in readme
