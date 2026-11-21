"""Hash chain over audit events: hash_n = sha256(hash_{n-1} || canonical(event_n))."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Optional

GENESIS_HASH = bytes(32)


def canonical_json(record: dict) -> bytes:
    """Stable serialisation: sorted keys, no whitespace, ISO timestamps as given."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()


def chain_hash(prev_hash: bytes, record: dict) -> bytes:
    return hashlib.sha256(prev_hash + canonical_json(record)).digest()


def verify_chain(rows: Iterable[tuple[int, bytes, bytes, dict]], start_hash: bytes = GENESIS_HASH) -> Optional[int]:
    """Check (id, prev_hash, hash, record) rows in id order.

    Returns the id of the first broken row, or None when the chain is intact.
    """
    expected_prev = start_hash
    for row_id, prev_hash, stored_hash, record in rows:
        if bytes(prev_hash) != expected_prev or chain_hash(expected_prev, record) != bytes(stored_hash):
            return row_id
        expected_prev = bytes(stored_hash)
    return None
