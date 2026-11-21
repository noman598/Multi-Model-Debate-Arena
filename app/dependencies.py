from typing import Optional
from fastapi import Depends, HTTPException, Request, status
import jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token


def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Extracts and validates the JWT access token.
    Checks the HTTP-only cookie first ('access_token').
    Falls back to the 'Authorization: Bearer <token>' header if cookie is absent.
    """
    token: Optional[str] = request.cookies.get("access_token")

    # Fallback to Authorization header if not in cookie (helpful for external API clients/Swagger)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: No access token provided in cookies or Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired. Please refresh your token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed access token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject in access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    user = db.query(User).filter(User.id == user_id_int).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with this token no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user
