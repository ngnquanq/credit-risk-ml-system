"""Append-only, hash-chained audit trail (E13)."""

from .chain import GENESIS_HASH, canonical_json, chain_hash, verify_chain
from .sanitizer import sanitize
from .writer import AuditEvent, AuditWriter, InMemoryAuditWriter, LoggingAuditWriter

__all__ = [
    "GENESIS_HASH",
    "AuditEvent",
    "AuditWriter",
    "InMemoryAuditWriter",
    "LoggingAuditWriter",
    "canonical_json",
    "chain_hash",
    "sanitize",
    "verify_chain",
]
