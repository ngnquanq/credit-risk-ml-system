"""Token verification (E11 AC1, AC7) against locally generated keys."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from entrypoints.api.security import InvalidToken, TokenVerifier

STAFF = "https://auth.test/realms/staff"
CUSTOMERS = "https://auth.test/realms/customers"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier():
    return TokenVerifier([STAFF, CUSTOMERS], "credit-api", "mfa", key_resolver=lambda iss, tok: KEY.public_key())


def _token(key=KEY, alg="RS256", **overrides):
    now = int(time.time())
    claims = {
        "iss": STAFF,
        "aud": ["credit-api"],
        "sub": "off-1",
        "iat": now,
        "exp": now + 300,
        "acr": "mfa",
        "branch_id": "HN01",
        "realm_access": {"roles": ["loan_officer", "offline_access"]},
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg)


def test_valid_staff_token(verifier):
    p = verifier.verify(_token())
    assert (p.sub, p.realm, p.roles, p.branch_id) == ("off-1", "staff", frozenset({"loan_officer"}), "HN01")


def test_valid_customer_token_ignores_branch(verifier):
    p = verifier.verify(_token(iss=CUSTOMERS, sub="cust-a", acr=None, realm_access={"roles": ["applicant"]}))
    assert (p.realm, p.roles, p.branch_id) == ("customers", frozenset({"applicant"}), None)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: _token(key=OTHER_KEY), id="wrong signing key"),
        pytest.param(lambda: _token(exp=int(time.time()) - 10), id="expired"),
        pytest.param(lambda: _token(aud=["other-api"]), id="wrong audience"),
        pytest.param(lambda: _token(iss="https://evil.test/realms/staff"), id="foreign issuer"),
        pytest.param(lambda: _token(acr=None), id="staff without mfa"),
        pytest.param(lambda: _token(realm_access={"roles": ["offline_access"]}), id="no application role"),
        pytest.param(lambda: _token(iss=CUSTOMERS, realm_access={"roles": ["loan_officer"]}), id="staff role in customer realm"),
        pytest.param(lambda: jwt.encode({"iss": STAFF, "sub": "x"}, None, algorithm="none"), id="alg none"),
        pytest.param(lambda: jwt.encode({"iss": STAFF, "sub": "x", "aud": "credit-api"}, "secret", algorithm="HS256"), id="hmac"),
        pytest.param(lambda: "not-a-jwt", id="garbage"),
    ],
)
def test_rejected_tokens(verifier, token):
    with pytest.raises(InvalidToken):
        verifier.verify(token())


def test_requires_at_least_one_issuer():
    with pytest.raises(ValueError):
        TokenVerifier([], "credit-api")
