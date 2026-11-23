"""Envelope encryption and keyed hashing for applicant personal data (ADR-0014).

- Each value is encrypted with its own random 256-bit data key (AES-256-GCM); the data key is
  wrapped with the active key-encryption key (KEK). The field name is authenticated data, so a
  ciphertext cannot be moved to another column unnoticed.
- KEKs form a keyring ``{key_id: key}``; the first is active, older ones only decrypt (rotation).
- Exact-match lookup of the citizen ID uses HMAC-SHA256 with a separate key, never a plain hash.
- Plain values never leave this module except through ``decrypt``; callers log and audit masks only.

Token format (ASCII): ``v1.<key_id>.<wrap_nonce>.<wrapped_dek>.<nonce>.<ciphertext>``, base64url parts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from collections.abc import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = "v1"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def parse_keyring(spec: str) -> dict[str, bytes]:
    """'k2:<base64 32 bytes>,k1:<...>' -> ordered keyring; the first key is active."""
    keyring: dict[str, bytes] = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        key_id, _, encoded = part.partition(":")
        key = _unb64(encoded)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", key_id) or len(key) != 32:
            raise ValueError("Each KEK must be '<id>:<base64 of 32 bytes>'")
        keyring[key_id] = key
    if not keyring:
        raise ValueError("At least one KEK is required")
    return keyring


def normalize_citizen_id(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 12:
        raise ValueError("Citizen ID must have 12 digits")
    return digits


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    if not re.fullmatch(r"0\d{9}", digits):
        raise ValueError("Phone must be a 10-digit Vietnamese number")
    return digits


def mask_citizen_id(last3: str) -> str:
    return f"••• ••• ••• {last3}"


def mask_phone(last3: str) -> str:
    return f"•••• ••• {last3}"


class PiiCipher:
    def __init__(self, keyring: Mapping[str, bytes], hmac_key: bytes):
        if not keyring:
            raise ValueError("At least one KEK is required")
        if len(hmac_key) < 32:
            raise ValueError("HMAC key must be at least 32 bytes")
        self._keyring = dict(keyring)
        self._active = next(iter(self._keyring))
        self._hmac_key = hmac_key

    @classmethod
    def from_settings(cls, keks: str, hmac_key_b64: str) -> PiiCipher:
        return cls(parse_keyring(keks), _unb64(hmac_key_b64))

    @property
    def active_key_id(self) -> str:
        return self._active

    def encrypt(self, field: str, plaintext: str) -> str:
        dek = AESGCM.generate_key(bit_length=256)
        nonce, wrap_nonce = os.urandom(12), os.urandom(12)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode(), field.encode())
        wrapped = AESGCM(self._keyring[self._active]).encrypt(wrap_nonce, dek, self._active.encode())
        return ".".join([_VERSION, self._active, _b64(wrap_nonce), _b64(wrapped), _b64(nonce), _b64(ciphertext)])

    def decrypt(self, field: str, token: str) -> str:
        version, key_id, wrap_nonce, wrapped, nonce, ciphertext = token.split(".")
        if version != _VERSION or key_id not in self._keyring:
            raise ValueError("Unknown token version or key")
        dek = AESGCM(self._keyring[key_id]).decrypt(_unb64(wrap_nonce), _unb64(wrapped), key_id.encode())
        return AESGCM(dek).decrypt(_unb64(nonce), _unb64(ciphertext), field.encode()).decode()

    def needs_rotation(self, token: str) -> bool:
        return token.split(".", 2)[1] != self._active

    def citizen_id_hmac(self, citizen_id: str) -> str:
        return hmac.new(self._hmac_key, normalize_citizen_id(citizen_id).encode(), hashlib.sha256).hexdigest()

    def owner_tag(self, subject: str) -> str:
        """Stable, non-reversible prefix for a user's uploads (no subject id in object keys)."""
        return hmac.new(self._hmac_key, f"owner:{subject}".encode(), hashlib.sha256).hexdigest()[:24]
