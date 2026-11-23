"""Applicant identity store (ADR-0014).

The only module that reads or writes ``applicant_identity``. Callers get either a masked view
(name plus the last three digits) or, through ``reveal``, the plain values for one customer;
the route that calls ``reveal`` authorizes and audits it first.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from infrastructure.persistence.models.sqlalchemy_models import (
    ApplicantIdentity,
    LoanApplication,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .crypto import (
    PiiCipher,
    mask_citizen_id,
    mask_phone,
    normalize_citizen_id,
    normalize_phone,
)


@dataclass(frozen=True)
class MaskedIdentity:
    full_name: str
    citizen_id_masked: str
    phone_masked: str

    def as_dict(self) -> dict:
        return {"full_name": self.full_name, "citizen_id_masked": self.citizen_id_masked,
                "phone_masked": self.phone_masked}


class IdentityRepository:
    def __init__(self, db: AsyncSession, cipher: PiiCipher):
        self._db = db
        self._cipher = cipher

    async def customer_ref_for(self, citizen_id: str) -> str | None:
        row = await self._by_hmac(self._cipher.citizen_id_hmac(citizen_id))
        return row.customer_ref if row else None

    async def resolve_or_create(self, full_name: str, citizen_id: str, phone: str) -> str:
        """Customer key for this citizen ID; a new identity is stored on first sight.

        An existing identity is never overwritten from a submission: changing a customer's
        recorded name or phone is a verified staff task, not something a form can do.
        """
        citizen_id, phone = normalize_citizen_id(citizen_id), normalize_phone(phone)
        digest = self._cipher.citizen_id_hmac(citizen_id)
        existing = await self._by_hmac(digest)
        if existing is not None:
            return existing.customer_ref
        row = ApplicantIdentity(
            customer_ref=await self._new_customer_ref(),
            citizen_id_hmac=digest,
            full_name_enc=self._cipher.encrypt("full_name", " ".join(full_name.split())),
            citizen_id_enc=self._cipher.encrypt("citizen_id", citizen_id),
            phone_enc=self._cipher.encrypt("phone", phone),
            citizen_id_last3=citizen_id[-3:],
            phone_last3=phone[-3:],
            key_id=self._cipher.active_key_id,
        )
        self._db.add(row)
        await self._db.flush()
        return row.customer_ref

    async def masked(self, customer_ref: str) -> MaskedIdentity | None:
        row = await self._by_ref(customer_ref)
        if row is None:
            return None
        return MaskedIdentity(
            full_name=self._cipher.decrypt("full_name", row.full_name_enc),
            citizen_id_masked=mask_citizen_id(row.citizen_id_last3),
            phone_masked=mask_phone(row.phone_last3),
        )

    async def reveal(self, customer_ref: str) -> dict | None:
        row = await self._by_ref(customer_ref)
        if row is None:
            return None
        return {
            "full_name": self._cipher.decrypt("full_name", row.full_name_enc),
            "citizen_id": self._cipher.decrypt("citizen_id", row.citizen_id_enc),
            "phone": self._cipher.decrypt("phone", row.phone_enc),
        }

    async def _by_hmac(self, digest: str) -> ApplicantIdentity | None:
        return (await self._db.execute(
            select(ApplicantIdentity).where(ApplicantIdentity.citizen_id_hmac == digest)
        )).scalar_one_or_none()

    async def _by_ref(self, customer_ref: str) -> ApplicantIdentity | None:
        return (await self._db.execute(
            select(ApplicantIdentity).where(ApplicantIdentity.customer_ref == customer_ref)
        )).scalar_one_or_none()

    async def _new_customer_ref(self) -> str:
        # Numeric like the historical keys, but in a range the Kaggle-derived history never uses.
        for _ in range(10):
            ref = str(900_000_000 + secrets.randbelow(99_999_999))
            taken = (await self._db.execute(
                select(LoanApplication.sk_id_curr).where(LoanApplication.sk_id_curr == ref)
            )).first() or await self._by_ref(ref)
            if not taken:
                return ref
        raise RuntimeError("Could not allocate a customer reference")
