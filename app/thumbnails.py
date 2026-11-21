import io

# AWS LAMBDA REUSE NOTE:
# This function is pure and standalone (bytes in -> bytes out).
# You can copy-paste it directly into an AWS Lambda handler triggered by S3 uploads.

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def generate_thumbnail(image_bytes: bytes, size: tuple = (200, 200)) -> bytes:
    """Generates a 200x200 thumbnail preserving aspect ratio."""
    if HAS_PILLOW:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail(size)
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=85)
            return output.getvalue()
    else:
        # Graceful fallback if Pillow is not yet installed in local environment
        return image_bytes
