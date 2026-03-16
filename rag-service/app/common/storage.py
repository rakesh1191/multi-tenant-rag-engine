"""MinIO / S3-compatible object storage client."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from uuid import UUID

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.common.exceptions import StorageException
from app.common.logging import get_logger
from app.config import settings

logger = get_logger(__name__)

_session = aioboto3.Session()


@asynccontextmanager
async def get_s3_client():
    """Async context manager for an S3 client."""
    async with _session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4"),
    ) as client:
        yield client


def build_s3_key(tenant_id: UUID, document_id: UUID, filename: str) -> str:
    """Construct the S3 object key for a document."""
    return f"tenants/{tenant_id}/documents/{document_id}/{filename}"


async def upload_file(
    file_content: bytes,
    s3_key: str,
    content_type: str,
    bucket: Optional[str] = None,
) -> str:
    """Upload a file to S3/MinIO and return the s3_key."""
    bucket = bucket or settings.S3_BUCKET
    try:
        async with get_s3_client() as client:
            await client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
            )
        logger.info("file_uploaded", s3_key=s3_key, size_bytes=len(file_content))
        return s3_key
    except ClientError as exc:
        logger.error("s3_upload_failed", s3_key=s3_key, error=str(exc))
        raise StorageException(f"Failed to upload file: {exc}") from exc


async def download_file(s3_key: str, bucket: Optional[str] = None) -> bytes:
    """Download a file from S3/MinIO and return its content."""
    bucket = bucket or settings.S3_BUCKET
    try:
        async with get_s3_client() as client:
            response = await client.get_object(Bucket=bucket, Key=s3_key)
            async with response["Body"] as stream:
                return await stream.read()
    except ClientError as exc:
        logger.error("s3_download_failed", s3_key=s3_key, error=str(exc))
        raise StorageException(f"Failed to download file: {exc}") from exc


async def delete_file(s3_key: str, bucket: Optional[str] = None) -> None:
    """Delete a file from S3/MinIO."""
    bucket = bucket or settings.S3_BUCKET
    try:
        async with get_s3_client() as client:
            await client.delete_object(Bucket=bucket, Key=s3_key)
        logger.info("file_deleted", s3_key=s3_key)
    except ClientError as exc:
        logger.error("s3_delete_failed", s3_key=s3_key, error=str(exc))
        raise StorageException(f"Failed to delete file: {exc}") from exc


async def generate_presigned_url(
    s3_key: str,
    expires_in: int = 3600,
    bucket: Optional[str] = None,
) -> str:
    """Generate a presigned URL for temporary access to an S3 object."""
    bucket = bucket or settings.S3_BUCKET
    try:
        async with get_s3_client() as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_key},
                ExpiresIn=expires_in,
            )
        return url
    except ClientError as exc:
        logger.error("presigned_url_failed", s3_key=s3_key, error=str(exc))
        raise StorageException(f"Failed to generate presigned URL: {exc}") from exc


async def ensure_bucket_exists(bucket: Optional[str] = None) -> None:
    """Create the S3 bucket if it does not already exist."""
    bucket = bucket or settings.S3_BUCKET
    try:
        async with get_s3_client() as client:
            try:
                await client.head_bucket(Bucket=bucket)
            except ClientError:
                await client.create_bucket(Bucket=bucket)
                logger.info("bucket_created", bucket=bucket)
    except ClientError as exc:
        logger.error("bucket_ensure_failed", bucket=bucket, error=str(exc))
        raise StorageException(f"Failed to ensure bucket: {exc}") from exc
