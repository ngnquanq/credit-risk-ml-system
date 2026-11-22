"""Envelope encryption, keyed hashing and masking for applicant personal data (ADR-0014)."""

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag
from identity import (
    PiiCipher,
    mask_citizen_id,
    mask_phone,
    normalize_citizen_id,
    normalize_phone,
)
from identity.crypto import parse_keyring


def _key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def cipher():
    return PiiCipher.from_settings(f"k1:{_key()}", _key())


def test_roundtrip_and_fresh_ciphertext_each_time(cipher):
    a = cipher.encrypt("full_name", "Nguyễn Văn An")
    b = cipher.encrypt("full_name", "Nguyễn Văn An")
    assert a != b
    assert cipher.decrypt("full_name", a) == "Nguyễn Văn An"
    assert "Nguy" not in a


def test_ciphertext_is_bound_to_its_field(cipher):
    token = cipher.encrypt("citizen_id", "001091234789")
    with pytest.raises(InvalidTag):
        cipher.decrypt("phone", token)


def test_wrong_key_cannot_decrypt(cipher):
    other = PiiCipher.from_settings(f"k1:{_key()}", _key())
    with pytest.raises(InvalidTag):
        other.decrypt("phone", cipher.encrypt("phone", "0912345245"))


def test_rotation_keeps_old_tokens_readable():
    old_key, new_key, hkey = _key(), _key(), _key()
    old = PiiCipher.from_settings(f"k1:{old_key}", hkey)
    token = old.encrypt("phone", "0912345245")
    rotated = PiiCipher.from_settings(f"k2:{new_key},k1:{old_key}", hkey)
    assert rotated.decrypt("phone", token) == "0912345245"
    assert rotated.needs_rotation(token)
    assert not rotated.needs_rotation(rotated.encrypt("phone", "0912345245"))


def test_citizen_id_hmac_is_keyed_and_normalised(cipher):
    assert cipher.citizen_id_hmac("001 091 234 789") == cipher.citizen_id_hmac("001091234789")
    other = PiiCipher.from_settings(f"k1:{_key()}", _key())
    assert other.citizen_id_hmac("001091234789") != cipher.citizen_id_hmac("001091234789")
    assert len(cipher.citizen_id_hmac("001091234789")) == 64


@pytest.mark.parametrize("bad", ["", "12345", "0010912347890", "abc"])
def test_invalid_citizen_ids_are_rejected(bad):
    with pytest.raises(ValueError):
        normalize_citizen_id(bad)


@pytest.mark.parametrize("raw, expected", [("0912 345 245", "0912345245"), ("+84 912 345 245", "0912345245")])
def test_phone_normalisation(raw, expected):
    assert normalize_phone(raw) == expected


def test_masks_show_only_the_last_three_digits():
    assert mask_citizen_id("789") == "••• ••• ••• 789"
    assert mask_phone("245") == "•••• ••• 245"


@pytest.mark.parametrize("spec", ["", "k1:short", "bad id:" + base64.urlsafe_b64encode(os.urandom(32)).decode()])
def test_keyring_validation(spec):
    with pytest.raises(ValueError):
        parse_keyring(spec)


def test_owner_tag_hides_the_subject(cipher):
    tag = cipher.owner_tag("22222222-2222-4222-8222-000000000001")
    assert len(tag) == 24 and "2222" not in tag
    assert tag == cipher.owner_tag("22222222-2222-4222-8222-000000000001")
