import os
from pathlib import Path
from app.config import settings

# Boto3 import with safe fallback
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


def _get_s3_client():
    """Initializes Boto3 S3 client using EC2 IAM Role or .env credentials."""
    kwargs = {"region_name": settings.AWS_REGION}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def save_file(file_bytes: bytes, filename: str, folder: str = "originals") -> str:
    """Saves file bytes to AWS S3 (or falls back to local disk)."""
    key = f"{folder}/{filename}"
    
    # Upload to AWS S3 if S3_BUCKET is configured
    if settings.S3_BUCKET and HAS_BOTO3:
        s3 = _get_s3_client()
        content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType=content_type
        )
        return key

    # Local fallback
    target_path = Path(settings.UPLOAD_DIR) / folder / filename
    with open(target_path, "wb") as f:
        f.write(file_bytes)
    return str(target_path)


def delete_file(filename: str, folder: str = "originals") -> bool:
    """Deletes a file from AWS S3 (or falls back to local disk)."""
    key = f"{folder}/{filename}"
    
    # Delete from AWS S3 if S3_BUCKET is configured
    if settings.S3_BUCKET and HAS_BOTO3:
        s3 = _get_s3_client()
        s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
        return True

    # Local fallback
    target_path = Path(settings.UPLOAD_DIR) / folder / filename
    if target_path.exists():
        os.remove(target_path)
        return True
    return False


def get_signed_url(filename: str, folder: str = "originals", expiration: int = None) -> str:
    """
    Generates a secure S3 Pre-signed URL so browser fetches images directly from S3.
    Falls back to local file URL if S3_BUCKET is not set.
    """
    if settings.S3_BUCKET and HAS_BOTO3:
        s3 = _get_s3_client()
        expires = expiration or settings.S3_URL_EXPIRATION_SECONDS
        key = f"{folder}/{filename}"
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expires
        )

    # Local fallback URL
    return f"/uploads/{folder}/{filename}"
