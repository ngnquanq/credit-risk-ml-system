"""Render the cluster's DB init ConfigMap from the schema files.

The SQL in services/loan-api/schema/ is the only copy of the schema. The ConfigMap that the
operational database mounts is generated from it, so the two cannot drift. The
init-ops-database.sql entry (the order in which files run, and the CDC publication) is kept
as it already is in the ConfigMap.

    python scripts/render_db_init_configmap.py            # rewrite the ConfigMap
    python scripts/render_db_init_configmap.py --check    # exit 1 if it is out of date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "services" / "loan-api" / "schema"
CONFIGMAP = ROOT / "platform" / "data" / "k8s" / "operational-db" / "03-db-init.yaml"
INIT_KEY = "init-ops-database.sql"
HEADER = """apiVersion: v1
kind: ConfigMap
metadata:
  name: db-init-scripts
  namespace: data-services
data:
"""


def _block(key: str, text: str) -> str:
    body = "\n".join(("    " + line) if line.strip() else "" for line in text.rstrip("\n").split("\n"))
    return f"  {key}: |\n{body}\n"


def init_entry(configmap_text: str) -> str:
    """The init-ops-database.sql entry as it is in an existing ConfigMap."""
    return yaml.safe_load(configmap_text)["data"][INIT_KEY]


def render(init_sql: str, schema_dir: Path = SCHEMA_DIR) -> str:
    out = HEADER + _block(INIT_KEY, init_sql)
    for path in sorted(schema_dir.glob("*.sql")):
        out += "\n" + _block(path.name, path.read_text(encoding="utf-8"))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    current = CONFIGMAP.read_text(encoding="utf-8")
    wanted = render(init_entry(current))
    if args.check:
        if yaml.safe_load(current) != yaml.safe_load(wanted):
            print(f"{CONFIGMAP.relative_to(ROOT)} is out of date; run scripts/render_db_init_configmap.py")
            return 1
        return 0
    CONFIGMAP.write_text(wanted, encoding="utf-8")
    print(f"Wrote {CONFIGMAP.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
