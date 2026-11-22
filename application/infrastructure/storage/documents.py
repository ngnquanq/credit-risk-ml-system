"""Applicant documents in S3-compatible storage (MinIO).

Browsers upload straight to storage with a presigned POST policy: the policy pins the object
key, the content type and the maximum size, so the API never streams files and a browser can
only write the one object it was given. The policy signature does not cover the host, which
lets the API sign with its internal endpoint while browsers post to the public origin.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from loguru import logger
from minio import Minio
from minio.datatypes import PostPolicy
from minio.error import S3Error


# Own threads and a deadline for storage calls (E15): a slow dependency elsewhere cannot hold
# up document checks, and a slow store fails the request instead of hanging it.
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="documents")
STAT_TIMEOUT_S = 5.0


class DocumentStore:
    def __init__(self, client: Minio, bucket: str, public_url: str, expiry: timedelta):
        self._client = client
        self._bucket = bucket
        self._public_url = public_url.rstrip("/")
        self._expiry = expiry

    @classmethod
    def from_settings(cls, settings) -> DocumentStore:
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value() if settings.minio_access_key else None,
            secret_key=settings.minio_secret_key.get_secret_value() if settings.minio_secret_key else None,
            secure=settings.minio_secure,
            region=settings.minio_region,
        )
        scheme = "https" if settings.minio_secure else "http"
        public = settings.minio_public_url or f"{scheme}://{settings.minio_endpoint}"
        return cls(client, settings.minio_bucket, public, timedelta(minutes=settings.minio_presigned_expiry_minutes))

    def upload_policy(self, key: str, content_type: str, max_bytes: int) -> tuple[str, dict[str, str]]:
        """URL and form fields for a single browser upload of ``key``."""
        policy = PostPolicy(self._bucket, datetime.now(timezone.utc) + self._expiry)
        policy.add_equals_condition("key", key)
        policy.add_equals_condition("Content-Type", content_type)
        policy.add_content_length_range_condition(1, max_bytes)
        fields = self._client.presigned_post_policy(policy)
        return f"{self._public_url}/{self._bucket}", {"key": key, "Content-Type": content_type, **fields}

    async def exists(self, key: str) -> bool:
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(_EXECUTOR, self._client.stat_object, self._bucket, key), STAT_TIMEOUT_S
            )
            return True
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                return False
            raise

    def ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"Created bucket {self._bucket}")
        except Exception as exc:  # storage down at startup must not stop the API (E15)
            logger.warning(f"Document storage not reachable at startup: {type(exc).__name__}")
