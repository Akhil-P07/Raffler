"""Environment configuration.

Validates required settings on startup. The app refuses to start if
SECRET_KEY is shorter than 32 bytes, so a weak JWT secret can never reach
production.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # SQLite default lets the app run locally with zero setup. Production sets
    # DATABASE_URL to the Railway PostgreSQL connection string.
    DATABASE_URL: str = "sqlite:///./raffler.db"

    SECRET_KEY: str = "dev-only-insecure-key-change-me-in-production-32b"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # Used to build QR registration URLs. Must be HTTPS in production.
    BASE_URL: str = "http://localhost:5173"

    # Bootstrap admin credentials (for POST /auth/login).
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "changeme"

    # Exact origin allowed by CORS.
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # The deployed API origin, injected into the CSP connect-src directive.
    API_ORIGIN: str = "http://localhost:8000"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 bytes. Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
