"""Feature catalog: definitions, model feature sets and reason codes (E2, E14).

Shared contract between training, scoring and the Loan API. This module only exposes
file locations so that consumers needing a single file do not import the catalog code.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETS_DIR = ROOT / "sets"
REASONS_FILE = ROOT / "reasons.yaml"
