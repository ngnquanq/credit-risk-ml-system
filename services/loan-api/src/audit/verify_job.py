#!/usr/bin/env python3
"""Daily audit chain verification (E13). Run: python -m audit.verify_job

Recomputes the hash chain from the last verified id and exits non-zero on a break.
Run as a Kubernetes CronJob with the audit_reader role plus SELECT on audit_event.

Env: AUDIT_DB_DSN (postgresql://...), AUDIT_VERIFY_FROM_ID (optional, default 1).
"""

from __future__ import annotations

import os
import sys
from datetime import timezone

from audit.chain import GENESIS_HASH, verify_chain


def _rows(cur, from_id: int):
    cur.execute(
        "SELECT id, prev_hash, hash, occurred_at, actor_sub, actor_realm, actor_roles, action, "
        "resource_type, resource_id, outcome, trace_id, details FROM audit_event WHERE id >= %s ORDER BY id",
        (from_id,),
    )
    for row in cur:
        (row_id, prev_hash, stored, occurred_at, sub, realm, roles, action, rtype, rid, outcome, trace_id, details) = row
        record = {
            # Writers hash the UTC ISO timestamp; normalise whatever timezone the session uses.
            "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
            "actor_sub": sub,
            "actor_realm": realm,
            "actor_roles": list(roles),
            "action": action,
            "resource_type": rtype,
            "resource_id": rid,
            "outcome": outcome,
            "trace_id": trace_id,
            "details": details,
        }
        yield row_id, bytes(prev_hash), bytes(stored), record


def main() -> int:
    import psycopg
    from loguru import logger
    from observability import configure_logging

    # stdout carries the probe lines below, so the log goes to stderr
    configure_logging(service="loan-api", component="audit-verify", stream=sys.stderr)

    from_id = int(os.getenv("AUDIT_VERIFY_FROM_ID", "1"))
    with psycopg.connect(os.environ["AUDIT_DB_DSN"]) as conn, conn.cursor() as cur:
        start = GENESIS_HASH
        if from_id > 1:
            cur.execute("SELECT hash FROM audit_event WHERE id < %s ORDER BY id DESC LIMIT 1", (from_id,))
            found = cur.fetchone()
            start = bytes(found[0]) if found else GENESIS_HASH
        broken = verify_chain(_rows(cur, from_id), start)
    if broken is not None:
        logger.critical("Audit chain is broken", event="audit.chain.tamper_detected", status="FAILURE",
                        action="verify_chain", target={"type": "audit_event", "id": str(broken)}, reason_code="hash_mismatch")
        print(f"audit_chain_ok 0\naudit_chain_first_broken_id {broken}")
        return 1
    logger.info("Audit chain verified", event="audit.chain.verified", status="SUCCESS", action="verify_chain")
    print("audit_chain_ok 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
