"""
Storage abstraction layer.

Supports two backends selected by STORAGE_PROVIDER env var:
  - "s3"  : AWS S3 or MinIO (default, uses aioboto3)
  - "gcs" : Google Cloud Storage (uses google-cloud-storage via executor)

Public API is identical regardless of backend:
    upload_file(key, data, content_type) -> str
    download_file(key) -> bytes
    delete_file(key) -> None
    ensure_bucket_exists() -> None

The module-level functions delegate to a lazily-created adapter singleton,
so all existing call sites (router, tasks, health check) require zero changes.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Protocol, runtime_checkable

from app.common.exceptions import StorageError
from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol (port definition — CLAUDE.md §3.3 / §4.3)
# ---------------------------------------------------------------------------

@runtime_checkable
class StoragePort(Protocol):
    async def upload_file(self, key: str, data: bytes, content_type: str) -> str: ...
    async def download_file(self, key: str) -> bytes: ...
    async def delete_file(self, key: str) -> None: ...
    async def ensure_bucket_exists(self) -> None: ...
    async def health_check(self) -> None: ...


# ---------------------------------------------------------------------------
# S3 / MinIO adapter (AWS + local dev)
# ---------------------------------------------------------------------------

class S3StorageAdapter:
    """aioboto3-backed adapter for AWS S3 and MinIO."""

    def __init__(self) -> None:
        import aioboto3
        self._session = aioboto3.Session()
        self._bucket = settings.S3_BUCKET

    def _client(self):
        kwargs: dict = {"region_name": settings.S3_REGION}
        # Use explicit credentials only when provided (MinIO / non-IRSA envs)
        if settings.S3_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY
            kwargs["aws_secret_access_key"] = settings.S3_SECRET_KEY
        if settings.S3_ENDPOINT:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT
        return self._session.client("s3", **kwargs)

    async def upload_file(self, key: str, data: bytes, content_type: str) -> str:
        async with self._client() as s3:
            try:
                await s3.put_object(
                    Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
                )
                return key
            except Exception as exc:
                raise StorageError(f"S3 upload failed: {exc}") from exc

    async def download_file(self, key: str) -> bytes:
        async with self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                return await response["Body"].read()
            except Exception as exc:
                raise StorageError(f"S3 download failed: {exc}") from exc

    async def delete_file(self, key: str) -> None:
        async with self._client() as s3:
            try:
                await s3.delete_object(Bucket=self._bucket, Key=key)
            except Exception as exc:
                raise StorageError(f"S3 delete failed: {exc}") from exc

    async def ensure_bucket_exists(self) -> None:
        from botocore.exceptions import ClientError
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                    await s3.create_bucket(Bucket=self._bucket)
                    logger.info("s3_bucket_created", bucket=self._bucket)
                else:
                    raise StorageError(f"S3 bucket check failed: {exc}") from exc

    async def health_check(self) -> None:
        from botocore.exceptions import ClientError
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except ClientError as exc:
                raise StorageError(f"S3 health check failed: {exc}") from exc


# ---------------------------------------------------------------------------
# GCS adapter (Google Cloud Storage)
# ---------------------------------------------------------------------------

class GCSStorageAdapter:
    """
    google-cloud-storage adapter for GCP deployments.

    The GCS client is synchronous, so all calls are offloaded to the default
    thread-pool executor to avoid blocking the async event loop (CLAUDE.md §2.4).

    Authentication uses Application Default Credentials (ADC):
    - On GKE: Workload Identity (no key file, no env var needed)
    - On local dev: `gcloud auth application-default login`
    - On other envs: GOOGLE_APPLICATION_CREDENTIALS env var
    """

    def __init__(self) -> None:
        try:
            from google.cloud import storage as gcs  # type: ignore[import]
            self._client = gcs.Client(project=settings.GCS_PROJECT_ID or None)
            self._bucket_name = settings.GCS_BUCKET or settings.S3_BUCKET
        except ImportError as exc:
            raise StorageError(
                "google-cloud-storage is not installed. "
                "Install it with: pip install 'rag-service[gcs]'"
            ) from exc

    def _run_sync(self, fn, *args, **kwargs):
        """Run a sync GCS call in the thread-pool executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))

    async def upload_file(self, key: str, data: bytes, content_type: str) -> str:
        def _upload():
            bucket = self._client.bucket(self._bucket_name)
            blob = bucket.blob(key)
            blob.upload_from_string(data, content_type=content_type)
            return key

        try:
            return await self._run_sync(_upload)
        except Exception as exc:
            raise StorageError(f"GCS upload failed: {exc}") from exc

    async def download_file(self, key: str) -> bytes:
        def _download():
            bucket = self._client.bucket(self._bucket_name)
            return bucket.blob(key).download_as_bytes()

        try:
            return await self._run_sync(_download)
        except Exception as exc:
            raise StorageError(f"GCS download failed: {exc}") from exc

    async def delete_file(self, key: str) -> None:
        def _delete():
            bucket = self._client.bucket(self._bucket_name)
            bucket.blob(key).delete()

        try:
            await self._run_sync(_delete)
        except Exception as exc:
            raise StorageError(f"GCS delete failed: {exc}") from exc

    async def ensure_bucket_exists(self) -> None:
        def _ensure():
            bucket = self._client.lookup_bucket(self._bucket_name)
            if bucket is None:
                self._client.create_bucket(
                    self._bucket_name,
                    location=settings.S3_REGION or "us-central1",
                )
                logger.info("gcs_bucket_created", bucket=self._bucket_name)

        try:
            await self._run_sync(_ensure)
        except Exception as exc:
            raise StorageError(f"GCS bucket ensure failed: {exc}") from exc

    async def health_check(self) -> None:
        def _check():
            return self._client.lookup_bucket(self._bucket_name)

        try:
            bucket = await self._run_sync(_check)
            if bucket is None:
                raise StorageError(
                    f"GCS bucket '{self._bucket_name}' not found"
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"GCS health check failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Factory + adapter singleton
# ---------------------------------------------------------------------------

_adapter: StoragePort | None = None


def get_storage_adapter() -> StoragePort:
    """Return the storage adapter singleton for the configured provider."""
    global _adapter
    if _adapter is None:
        provider = settings.STORAGE_PROVIDER.lower()
        if provider == "gcs":
            _adapter = GCSStorageAdapter()
            logger.info("storage_adapter_initialized", provider="gcs")
        else:
            _adapter = S3StorageAdapter()
            logger.info("storage_adapter_initialized", provider="s3")
    return _adapter


# ---------------------------------------------------------------------------
# Public module-level API — preserves all existing call sites unchanged
# ---------------------------------------------------------------------------

async def upload_file(key: str, data: bytes, content_type: str) -> str:
    return await get_storage_adapter().upload_file(key, data, content_type)


async def download_file(key: str) -> bytes:
    return await get_storage_adapter().download_file(key)


async def delete_file(key: str) -> None:
    await get_storage_adapter().delete_file(key)


async def ensure_bucket_exists() -> None:
    await get_storage_adapter().ensure_bucket_exists()
