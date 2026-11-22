"""Issue upload policies and validate document references for loan applications."""

import re
import uuid

from fastapi import HTTPException, status
from identity import PiiCipher
from infrastructure.storage.documents import DocumentStore
from loguru import logger


# Document slot -> folder. The portals use 2 (citizen ID card, front), 15 (back) and 3 (income proof).
DOCUMENT_FOLDERS = {
    2: "identity",           # Citizen ID card, front
    3: "financial/income",   # Income proof (payslips, salary statement)
    4: "employment",         # Employment certificate
    5: "financial/banking",  # Bank statement
    6: "personal",           # Utility bills
    7: "personal",           # Property ownership
    8: "personal",           # Vehicle registration
    9: "financial/insurance",  # Insurance policy
    10: "financial/tax",     # Tax returns
    11: "personal",          # Medical certificate
    12: "personal",          # Education certificate
    13: "personal",          # Marriage certificate
    14: "personal",          # Divorce certificate
    15: "identity",          # Citizen ID card, back
    16: "financial/pension",  # Pension certificate
    17: "personal",          # Military service
    18: "employment",        # Business license
    19: "financial/credit",  # Credit report
    20: "employment",        # Reference letter
    21: "other",             # Other document
}
CONTENT_TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
# Self-service applicants must send both sides of the citizen ID card; at a branch the officer
# checks the physical card and records it in a case note.
REQUIRED_SELF_SERVICE_DOCUMENTS = ("document_id_2", "document_id_15")
_DOCUMENT_ID = re.compile(r"^(?P<owner>[0-9a-f]{24})/[a-z/]+/doc_[0-9a-f]{32}\.(pdf|jpg|png)$")


class DocumentUploads:
    def __init__(self, cipher: PiiCipher, store: DocumentStore, max_bytes: int, subject: str):
        self._cipher = cipher
        self._store = store
        self.max_bytes = max_bytes
        self._subject = subject

    def presign(self, document_type: int, content_type: str) -> tuple[str, str, dict[str, str]]:
        """Issue a policy for one object under the authenticated uploader's prefix."""
        folder = DOCUMENT_FOLDERS.get(document_type)
        if folder is None:
            raise HTTPException(status_code=400, detail=f"Invalid document type: {document_type}")
        owner = self._cipher.owner_tag(self._subject)
        key = f"{owner}/{folder}/doc_{uuid.uuid4().hex}.{CONTENT_TYPES[content_type]}"
        try:
            url, fields = self._store.upload_policy(key, content_type, self.max_bytes)
        except Exception as exc:
            logger.error(f"Could not sign an upload policy: {type(exc).__name__}")
            raise HTTPException(status_code=503, detail="Document storage is unavailable") from exc
        return key, url, fields

    async def validate(
        self,
        document_ids: dict[str, str] | None,
        *,
        require_identity: bool = False,
    ) -> None:
        """Require owned, uploaded objects and both ID sides for self-service intake."""
        document_ids = document_ids or {}
        if require_identity:
            missing = [slot for slot in REQUIRED_SELF_SERVICE_DOCUMENTS if not document_ids.get(slot)]
            if missing:
                raise HTTPException(status_code=422, detail={"error": "documents_required", "slots": missing})
        owner = self._cipher.owner_tag(self._subject)
        for slot, document_id in document_ids.items():
            match = _DOCUMENT_ID.fullmatch(document_id or "")
            if match is None or match["owner"] != owner:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "document_not_owned", "slot": slot},
                )
            try:
                uploaded = await self._store.exists(document_id)
            except Exception as exc:
                logger.warning(f"Document storage unavailable: {type(exc).__name__}")
                raise HTTPException(status_code=503, detail="Document storage is unavailable") from exc
            if not uploaded:
                raise HTTPException(status_code=422, detail={"error": "document_not_uploaded", "slot": slot})
