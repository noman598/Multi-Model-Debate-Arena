from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional
import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """
    Creates a signed JWT access token.
    Returns: (encoded_token_string, expires_in_seconds)
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
        expires_in = int(expires_delta.total_seconds())
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 10

    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt, expires_in


def decode_access_token(token: str) -> dict:
    """
    Decodes and validates a JWT access token.
    Raises jwt.ExpiredSignatureError if expired, or jwt.PyJWTError if invalid.
    """
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM]
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token is not an access token")
    return payload


def generate_refresh_token() -> str:
    """Generates a cryptographically strong random refresh token."""
    return secrets.token_urlsafe(64)
