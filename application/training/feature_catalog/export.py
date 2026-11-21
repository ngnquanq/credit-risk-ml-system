"""Generate artifacts that other build contexts need from the feature catalog (E2, E14).

Usage:
    python application/training/feature_catalog/export.py reason-map OUT.json

The scoring Bento cannot import the catalog (separate Docker context), so the builder
writes ``reason_map.json`` next to the model: feature -> reason code, for explainable
features only (protected, sensitive and proxy features never become reasons).

Generating the Feast schemas and the Flink sink columns from the definitions is the
next step of E2 and is not implemented yet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from feature_catalog.catalog import Catalog  # type: ignore[no-redef]
else:
    from .catalog import Catalog


def reason_map(catalog: Catalog, features: list[str] | None = None) -> dict[str, str]:
    names = features if features is not None else catalog.names()
    return {name: code for name in names if (code := catalog.reason_code(name)) is not None}


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "reason-map":
        print(__doc__)
        return 2
    out = Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reason_map(Catalog.load()), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
