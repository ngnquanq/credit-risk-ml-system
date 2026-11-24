"""contracts/telemetry/events.json and the code that emits those events say the same thing."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CATALOG = json.loads((ROOT / "contracts" / "telemetry" / "events.json").read_text())
SCHEMA = json.loads((ROOT / "contracts" / "telemetry" / "log_schema.json").read_text())
EVENTS = {e["event"]: e for e in CATALOG["events"]}
MODULES = tuple(CATALOG["modules"])
CONTRACT_FIELDS = set(SCHEMA["properties"]) - {"timestamp", "level", "service", "component", "module", "event", "message"}

# An event name written as event="x.y" in a call, anywhere under services/
LITERAL = re.compile(r'\bevent\s*=\s*"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"')


def emitted() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in (ROOT / "services").rglob("*.py"):
        for name in LITERAL.findall(path.read_text()):
            found.setdefault(name, []).append(path.relative_to(ROOT).as_posix())
    return found


def test_the_schema_rule_covers_exactly_the_catalogued_modules():
    pattern = SCHEMA["allOf"][0]["if"]["properties"]["event"]["pattern"]
    assert pattern == "^(" + "|".join(MODULES) + ")\\."


def test_every_catalogued_event_is_well_formed():
    for name, entry in EVENTS.items():
        assert name.startswith(tuple(m + "." for m in MODULES)), name
        assert entry["level"] in {"INFO", "WARNING", "ERROR", "CRITICAL"}, name
        assert "status" in entry["requires"], f"{name} must require status"
        assert set(entry["requires"]) <= CONTRACT_FIELDS, f"{name}: {set(entry['requires']) - CONTRACT_FIELDS}"
        assert entry["means"], name


def test_the_code_emits_no_audit_class_event_the_catalog_does_not_list():
    unlisted = {n: where for n, where in emitted().items() if n.startswith(tuple(m + "." for m in MODULES)) and n not in EVENTS}
    assert unlisted == {}, f"Add these to contracts/telemetry/events.json: {unlisted}"


def test_every_catalogued_event_is_emitted_somewhere():
    seen = emitted()
    missing = sorted(n for n in EVENTS if n not in seen)
    assert missing == [], f"Catalogued but never emitted: {missing}"
