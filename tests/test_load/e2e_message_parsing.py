"""Message parsing helpers for E2E load-test monitors."""

from __future__ import annotations

import base64
import json
from typing import Any


def unwrap_cloudevent(payload: Any) -> Any:
    """Return CloudEvent data when present, otherwise the original payload."""
    if isinstance(payload, dict) and "specversion" in payload:
        if "data" in payload:
            return payload.get("data")
        if "data_base64" in payload:
            try:
                return base64.b64decode(str(payload["data_base64"])).decode("utf-8")
            except Exception:
                return payload
    return payload


def extract_sk_id_curr(payload: Any) -> str | None:
    """Extract sk_id_curr from plain, CloudEvent, or nested Kafka payloads."""
    if isinstance(payload, dict) and "specversion" in payload:
        for key in ("subject", "ce-subject"):
            value = payload.get(key)
            if value:
                return str(value)

    payload = unwrap_cloudevent(payload)
    stack = [payload]
    seen = 0
    while stack and seen < 64:
        seen += 1
        current = stack.pop()
        if isinstance(current, str):
            try:
                decoded = json.loads(current)
            except json.JSONDecodeError:
                continue
            stack.append(decoded)
            continue
        if isinstance(current, dict):
            for key, value in current.items():
                normalized_key = str(key).lower()
                if normalized_key in {"sk_id_curr", "skidcurr", "sk_id"} and value is not None:
                    return str(value)
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
    return None
