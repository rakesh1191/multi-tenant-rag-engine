import aioboto3
from botocore.exceptions import ClientError
from app.config import settings
from app.common.exceptions import StorageError
from app.common.logging import get_logger

logger = get_logger(__name__)

_session = aioboto3.Session()


def get_s3_client():
    return _session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


async def ensure_bucket_exists() -> None:
    async with get_s3_client() as s3:
        try:
            await s3.head_bucket(Bucket=settings.S3_BUCKET)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                await s3.create_bucket(Bucket=settings.S3_BUCKET)
                logger.info("s3_bucket_created", bucket=settings.S3_BUCKET)
            else:
                raise StorageError(f"Failed to check bucket: {e}") from e


async def upload_file(key: str, data: bytes, content_type: str) -> str:
    async with get_s3_client() as s3:
        try:
            await s3.put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            return key
        except ClientError as e:
            raise StorageError(f"Upload failed: {e}") from e


async def download_file(key: str) -> bytes:
    async with get_s3_client() as s3:
        try:
            response = await s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
            return await response["Body"].read()
        except ClientError as e:
            raise StorageError(f"Download failed: {e}") from e


async def delete_file(key: str) -> None:
    async with get_s3_client() as s3:
        try:
            await s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
        except ClientError as e:
            raise StorageError(f"Delete failed: {e}") from e
