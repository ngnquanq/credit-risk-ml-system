#!/usr/bin/env python3
"""Export the Loan API's OpenAPI schema to contracts/openapi/loan-api.json (ADR-0011).

The portals generate their TypeScript client from this file. CI regenerates it and
fails on a diff (`make contracts && git diff --exit-code contracts/`).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "openapi" / "loan-api.json"


def main() -> int:
    sys.path.insert(0, str(ROOT / "services" / "loan-api" / "src"))
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    # Importing the app must not reach MinIO or a trace collector.
    with patch("minio.Minio", MagicMock()):
        from entrypoints.api.main import app

    schema = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
