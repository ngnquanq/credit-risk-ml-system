"""The cluster's DB init ConfigMap must be generated from services/loan-api/schema (no drift)."""

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("render_db_init", ROOT / "scripts" / "render_db_init_configmap.py")
render_db_init = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_db_init)


def test_configmap_matches_the_schema_files():
    current = render_db_init.CONFIGMAP.read_text(encoding="utf-8")
    wanted = render_db_init.render(render_db_init.init_entry(current))
    assert yaml.safe_load(current) == yaml.safe_load(wanted), (
        "03-db-init.yaml is out of date: run python scripts/render_db_init_configmap.py"
    )


def test_every_schema_file_is_listed_in_the_init_script():
    init = render_db_init.init_entry(render_db_init.CONFIGMAP.read_text(encoding="utf-8"))
    for path in sorted(render_db_init.SCHEMA_DIR.glob("*.sql")):
        assert f"\\i /schemas/{path.name}" in init, f"{path.name} is not applied by init-ops-database.sql"
