import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "FastAPI PicShare Auth"
    SECRET_KEY: str = "supersecretjwtkeyforauthenticationpleasereplaceinproduction1234567890"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database URL (SQLite or PostgreSQL / RDS)
    DATABASE_URL: str = "sqlite:///./auth_database.db"
    
    # Redis configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_REAL_REDIS: bool = False
    
    # Cookie settings
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: Optional[str] = None
    
    # Photo storage settings (Local or S3)
    UPLOAD_DIR: str = "uploads"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

# Ensure local directories exist
os.makedirs(f"{settings.UPLOAD_DIR}/originals", exist_ok=True)
os.makedirs(f"{settings.UPLOAD_DIR}/thumbnails", exist_ok=True)
