from datetime import datetime
import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username must be 3-50 chars")
    email: str = Field(..., max_length=100, description="Valid email address")
    full_name: Optional[str] = Field(None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain alphanumeric characters, underscores, and hyphens")
        return v


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100, description="Password must be at least 6 characters")


class UserLogin(BaseModel):
    username_or_email: str = Field(..., description="Username or email address")
    password: str = Field(..., description="User password")


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    message: str
    token_type: str = "bearer"
    access_token_expires_in: int
    user: UserResponse


class RefreshTokenResponse(BaseModel):
    message: str
    token_type: str = "bearer"
    access_token_expires_in: int


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
