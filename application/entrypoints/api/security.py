"""Bearer token verification (E11, ADR-0012).

Accepts RS256 access tokens from the configured Keycloak realms only, with the API's
audience, and turns them into a ``Principal``. Everything else is a 401.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Iterable, Optional

import jwt
from fastapi import Header, HTTPException, status

from authz import Principal
from authz.policy import CUSTOMER_ROLES, STAFF_REALM, STAFF_ROLES

KeyResolver = Callable[[str, str], object]  # (issuer, token) -> public key


class InvalidToken(Exception):
    pass


def _keycloak_key_resolver(ttl_seconds: int) -> KeyResolver:
    clients: dict[str, jwt.PyJWKClient] = {}

    def resolve(issuer: str, token: str):
        client = clients.get(issuer)
        if client is None:
            client = jwt.PyJWKClient(
                f"{issuer}/protocol/openid-connect/certs", cache_jwk_set=True, lifespan=ttl_seconds
            )
            clients[issuer] = client
        return client.get_signing_key_from_jwt(token).key

    return resolve


class TokenVerifier:
    def __init__(
        self,
        issuers: Iterable[str],
        audience: str,
        staff_required_acr: str = "mfa",
        key_resolver: Optional[KeyResolver] = None,
        jwks_ttl_seconds: int = 300,
    ):
        self.issuers = {i.rstrip("/") for i in issuers}
        if not self.issuers:
            raise ValueError("At least one trusted issuer is required")
        self.audience = audience
        self.staff_required_acr = staff_required_acr
        self._resolve = key_resolver or _keycloak_key_resolver(jwks_ttl_seconds)

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256":
                raise InvalidToken("unsupported algorithm")
            issuer = str(jwt.decode(token, options={"verify_signature": False}).get("iss", "")).rstrip("/")
            if issuer not in self.issuers:
                raise InvalidToken("untrusted issuer")
            claims = jwt.decode(
                token,
                self._resolve(issuer, token),
                algorithms=["RS256"],
                audience=self.audience,
                issuer=issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except InvalidToken:
            raise
        except jwt.PyJWTError as exc:
            raise InvalidToken(str(exc)) from exc

        realm = issuer.rsplit("/realms/", 1)[-1]
        known = STAFF_ROLES if realm == STAFF_REALM else CUSTOMER_ROLES
        # Keycloak adds default roles (offline_access, uma_authorization); keep only ours.
        roles = frozenset(claims.get("realm_access", {}).get("roles", [])) & known
        if not roles:
            raise InvalidToken("no application role")
        if realm == STAFF_REALM and self.staff_required_acr and claims.get("acr") != self.staff_required_acr:
            raise InvalidToken("staff token without multi-factor authentication")
        try:
            return Principal(
                sub=claims["sub"],
                realm=realm,
                roles=roles,
                branch_id=claims.get("branch_id") if realm == STAFF_REALM else None,
            )
        except ValueError as exc:
            raise InvalidToken(str(exc)) from exc


@lru_cache(maxsize=1)
def _verifier() -> TokenVerifier:
    from core import settings

    return TokenVerifier(
        settings.oidc_issuer_list,
        settings.oidc_audience,
        settings.oidc_staff_required_acr,
        jwks_ttl_seconds=settings.oidc_jwks_ttl_seconds,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="credit-api"'},
    )


async def get_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    """FastAPI dependency for every /api/v1 route."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("missing bearer token")
    try:
        return _verifier().verify(authorization.split(" ", 1)[1].strip())
    except InvalidToken as exc:
        raise _unauthorized(f"invalid token: {exc}") from None
    except ValueError as exc:  # no issuers configured
        raise _unauthorized(str(exc)) from None
