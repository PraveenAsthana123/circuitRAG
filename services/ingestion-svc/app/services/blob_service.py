"""
Blob storage wrapper (Design Areas 35 — Knowledge Lifecycle, 7 — Data Plane).

Stores the raw uploaded file in MinIO (S3-compatible) so we can:

* Re-process the document if parsing or embedding improves later.
* Prove provenance during audits / compliance reviews.
* Serve the original to admins via a signed download URL.
"""
from __future__ import annotations

import io
import logging
from uuid import UUID

from documind_core.exceptions import DataError
from minio import Minio
from minio.error import S3Error

log = logging.getLogger(__name__)


class BlobService:
    """
    Tenant-scoped object paths: ``tenant/<tenant_id>/doc/<document_id>/<filename>``.

    Bucket is created on first use (idempotent).
    """

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        use_ssl: bool = False,
    ) -> None:
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=use_ssl)
        self._bucket = bucket

    def ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                log.info("blob_bucket_created name=%s", self._bucket)
        except S3Error as exc:
            raise DataError(f"MinIO bucket error: {exc}") from exc

    @staticmethod
    def build_object_name(tenant_id: str, document_id: UUID, filename: str) -> str:
        return f"tenant/{tenant_id}/doc/{document_id}/{filename}"

    def put(self, *, tenant_id: str, document_id: UUID, filename: str, data: bytes, content_type: str) -> str:
        object_name = self.build_object_name(tenant_id, document_id, filename)
        try:
            self._client.put_object(
                self._bucket,
                object_name,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except S3Error as exc:
            raise DataError(f"MinIO upload failed: {exc}") from exc
        uri = f"s3://{self._bucket}/{object_name}"
        log.info("blob_put uri=%s size=%d", uri, len(data))
        return uri

    def delete(self, *, uri: str) -> None:
        # uri looks like s3://bucket/path; parse the path portion
        if not uri.startswith("s3://"):
            raise ValueError(f"Not an s3 uri: {uri!r}")
        _, rest = uri.split("s3://", 1)
        _, object_name = rest.split("/", 1)
        try:
            self._client.remove_object(self._bucket, object_name)
        except S3Error as exc:
            log.warning("blob_delete_failed uri=%s err=%s", uri, exc)
