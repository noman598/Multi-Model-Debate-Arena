import os
from pathlib import Path
from app.config import settings

# AWS S3 MIGRATION NOTE:
# To migrate to Amazon S3, replace the file writes below with:
# s3 = boto3.client('s3')
# s3.put_object(Bucket=S3_BUCKET, Key=f"{folder}/{filename}", Body=file_bytes)
# s3.delete_object(Bucket=S3_BUCKET, Key=f"{folder}/{filename}")


def save_file(file_bytes: bytes, filename: str, folder: str = "originals") -> str:
    """Saves file bytes to storage (local disk or S3)."""
    target_path = Path(settings.UPLOAD_DIR) / folder / filename
    with open(target_path, "wb") as f:
        f.write(file_bytes)
    return str(target_path)


def delete_file(filename: str, folder: str = "originals") -> bool:
    """Deletes a file from storage."""
    target_path = Path(settings.UPLOAD_DIR) / folder / filename
    if target_path.exists():
        os.remove(target_path)
        return True
    return False
