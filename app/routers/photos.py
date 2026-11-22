from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Photo, User
from app.notifications import send_photo_notification
from app.storage import delete_file, get_signed_url, save_file
from app.thumbnails import generate_thumbnail

router = APIRouter(prefix="/api/photos", tags=["Photos"])


@router.get("", summary="Get all photos uploaded by the current user")
def get_user_photos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns all photos for the authenticated user.
    Uses AWS S3 Pre-signed URLs for both original and thumbnail images.
    """
    photos = db.query(Photo).filter(
        Photo.user_id == current_user.id
    ).order_by(Photo.created_at.desc()).all()

    return [
        {
            "id": p.id,
            "filename": p.filename,
            "thumbnail_filename": p.thumbnail_filename,
            "original_url": get_signed_url(p.filename, folder="originals"),
            "thumbnail_url": get_signed_url(p.thumbnail_filename, folder="thumbnails"),
            "created_at": p.created_at.isoformat()
        }
        for p in photos
    ]


@router.post("/upload", status_code=status.HTTP_201_CREATED, summary="Upload photo (JPG/PNG, max 5MB)")
async def upload_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Uploads a photo for the authenticated user:
    1. Validates extension (JPG/PNG) and size (max 5 MB)
    2. Uploads original and 200x200 thumbnail to S3 (or local disk)
    3. Saves record in database
    4. Returns S3 pre-signed URLs
    """
    # 1. Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPG, JPEG, and PNG images are allowed."
        )

    # 2. Validate max file size (5 MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the maximum limit of 5 MB."
        )

    # 3. Generate unique filenames
    uid = uuid.uuid4().hex
    filename = f"{uid}{ext}"
    thumb_filename = f"thumb_{uid}.jpg"

    # 4. Save original and generate thumbnail to S3/local
    save_file(contents, filename, folder="originals")
    thumb_bytes = generate_thumbnail(contents, size=(200, 200))
    save_file(thumb_bytes, thumb_filename, folder="thumbnails")

    # 5. Save database record
    photo = Photo(
        user_id=current_user.id,
        filename=filename,
        thumbnail_filename=thumb_filename
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    # 6. Trigger notification
    send_photo_notification(current_user.id, photo.id, filename)

    return {
        "message": "Photo uploaded and processed successfully",
        "photo": {
            "id": photo.id,
            "filename": photo.filename,
            "original_url": get_signed_url(photo.filename, folder="originals"),
            "thumbnail_url": get_signed_url(photo.thumbnail_filename, folder="thumbnails"),
            "created_at": photo.created_at.isoformat()
        }
    }


@router.delete("/{photo_id}", summary="Delete a photo")
def delete_user_photo(
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deletes photo and thumbnail from S3/storage and removes the database record."""
    photo = db.query(Photo).filter(
        Photo.id == photo_id,
        Photo.user_id == current_user.id
    ).first()

    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found or you do not have permission to delete it"
        )

    # Delete files from S3/storage
    delete_file(photo.filename, folder="originals")
    delete_file(photo.thumbnail_filename, folder="thumbnails")

    # Delete database record
    db.delete(photo)
    db.commit()

    return {"message": f"Photo #{photo_id} deleted successfully"}
