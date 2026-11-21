from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.redis_client import redis_store
from app.schemas import (
    MessageResponse,
    RefreshTokenResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    access_token_expires_in: int,
) -> None:
    """Sets secure HTTP-only cookies for access and refresh tokens."""
    # Access token cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=access_token_expires_in,
        expires=access_token_expires_in,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )

    # Refresh token cookie (valid for REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=refresh_max_age,
        expires=refresh_max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    """Clears authentication cookies."""
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key="refresh_token",
        path="/",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """Creates a new user in SQLite after verifying username and email uniqueness."""
    existing_user = db.query(User).filter(
        or_(User.username == user_in.username, User.email == user_in.email)
    ).first()

    if existing_user:
        if existing_user.username == user_in.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this username already exists",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists",
            )

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with username/email and password",
)
def login(
    login_data: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticates user, creates JWT access token and secure refresh token.
    Stores refresh token in Redis and sets HTTP-only cookies.
    """
    user = db.query(User).filter(
        or_(
            User.username == login_data.username_or_email,
            User.email == login_data.username_or_email,
        )
    ).first()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Generate tokens
    access_token, expires_in = create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    refresh_token = generate_refresh_token()

    # Store refresh token in Redis with TTL
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    redis_store.store_refresh_token(
        token=refresh_token,
        user_id=user.id,
        username=user.username,
        ttl_seconds=ttl_seconds,
    )

    # Set both tokens in HTTP-only cookies
    set_auth_cookies(
        response=response,
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=expires_in,
    )

    return TokenResponse(
        message="Login successful",
        token_type="bearer",
        access_token_expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token using stored refresh token cookie",
)
def refresh_token_endpoint(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Validates refresh token stored in HTTP-only cookie against Redis.
    Performs token rotation: revokes the old refresh token, generates a new one,
    and issues a new JWT access token in cookies.
    """
    # Extract refresh token from cookie
    refresh_token: Optional[str] = request.cookies.get("refresh_token")

    # Optional header fallback for testing / non-browser clients
    if not refresh_token:
        refresh_token = request.headers.get("X-Refresh-Token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing from request cookies",
        )

    # Lookup token in Redis
    token_data = redis_store.get_refresh_token(refresh_token)
    if not token_data:
        # Token not found or expired in Redis
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token. Please log in again.",
        )

    user_id = token_data.get("user_id")
    if not user_id:
        redis_store.delete_refresh_token(refresh_token)
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Corrupted refresh token session",
        )

    # Verify user in database
    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user or not user.is_active:
        redis_store.delete_refresh_token(refresh_token)
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer active",
        )

    # Token Rotation: Revoke old refresh token from Redis
    redis_store.delete_refresh_token(refresh_token)

    # Create brand new access and refresh tokens
    new_access_token, expires_in = create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    new_refresh_token = generate_refresh_token()

    # Store new refresh token in Redis
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    redis_store.store_refresh_token(
        token=new_refresh_token,
        user_id=user.id,
        username=user.username,
        ttl_seconds=ttl_seconds,
    )

    # Update cookies on response
    set_auth_cookies(
        response=response,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        access_token_expires_in=expires_in,
    )

    return RefreshTokenResponse(
        message="Access token refreshed successfully",
        token_type="bearer",
        access_token_expires_in=expires_in,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out and revoke refresh token",
)
def logout(
    request: Request,
    response: Response,
):
    """
    Revokes the refresh token from Redis and clears authentication cookies.
    """
    refresh_token = request.cookies.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if refresh_token:
        redis_store.delete_refresh_token(refresh_token)

    clear_auth_cookies(response)
    return MessageResponse(message="Logged out successfully")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Protected endpoint: Returns the profile of the user authenticated via JWT cookie."""
    return current_user


@router.get(
    "/status",
    summary="Check current authentication and session status",
)
def auth_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Safe session probe for frontend on page load.
    Does not throw 401 error; returns current auth state and Redis info.
    """
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    user_info = None
    is_authenticated = False
    needs_refresh = False

    if access_token:
        try:
            payload = decode_access_token(access_token)
            user_id = payload.get("sub")
            if user_id:
                user = db.query(User).filter(User.id == int(user_id)).first()
                if user and user.is_active:
                    user_info = UserResponse.model_validate(user).model_dump()
                    is_authenticated = True
        except Exception:
            needs_refresh = True
    elif refresh_token:
        needs_refresh = True

    return {
        "authenticated": is_authenticated,
        "needs_refresh": needs_refresh,
        "user": user_info,
        "redis_mode": "in-memory (fakeredis fallback)" if redis_store.is_fallback else "live redis server",
        "has_access_cookie": bool(access_token),
        "has_refresh_cookie": bool(refresh_token),
    }
