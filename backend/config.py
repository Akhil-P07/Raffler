"""Environment configuration.

Validates required settings on startup. The app refuses to start if
SECRET_KEY is shorter than 32 bytes, so a weak JWT secret can never reach
production.
"""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder dev key. The app refuses to start while SECRET_KEY equals it,
# so a known signing key can never reach a real deployment. Set a real
# SECRET_KEY (env or backend/.env) even for local dev.
_INSECURE_DEFAULT_SECRET = "dev-only-insecure-key-change-me-in-production-32b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # SQLite is the only backend. Local dev uses a file in the working dir;
    # production points this at a file on the mounted persistent volume, e.g.
    # DATABASE_URL=sqlite:////data/raffler.db
    DATABASE_URL: str = "sqlite:///./raffler.db"

    SECRET_KEY: str = _INSECURE_DEFAULT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # super-admin token
    SESSION_TOKEN_EXPIRE_MINUTES: int = 720  # user dashboard session (12h)

    # Google OAuth (optional). If CLIENT_ID/SECRET are unset, the Google login
    # endpoints return 503 and only email/password login works.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Where Google redirects back (must match the Google Cloud console config).
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # Comma-separated emails granted the club (premium) plan, in addition to the
    # admin-managed DB allowlist. Self-signup is open to everyone (free tier).
    PREMIUM_EMAILS: str = ""

    # Brevo (transactional email API) for emailing the buyer their ticket PDF on
    # registration. If BREVO_API_KEY is unset, emailing is silently disabled
    # (registration still succeeds). The sender email must be a verified Brevo
    # sender/domain.
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = ""
    BREVO_SENDER_NAME: str = "Raffler"

    # Used to build QR registration URLs. Must be HTTPS in production.
    BASE_URL: str = "http://localhost:5173"

    # Bootstrap admin credentials (for POST /auth/login).
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "changeme"

    # Exact origin allowed by CORS.
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # The deployed API origin, injected into the CSP connect-src directive.
    API_ORIGIN: str = "http://localhost:8000"

    @property
    def premium_email_set(self) -> set[str]:
        return {
            e.strip().lower()
            for e in self.PREMIUM_EMAILS.split(",")
            if e.strip()
        }

    @property
    def google_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def email_enabled(self) -> bool:
        return bool(self.BREVO_API_KEY and self.BREVO_SENDER_EMAIL)

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v.encode("utf-8")) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 bytes. Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
            )
        if v == _INSECURE_DEFAULT_SECRET:
            # The default is publicly known; signing tokens with it is unsafe.
            raise ValueError(
                "SECRET_KEY is still the built-in dev default. Set a real one "
                "(see the command above) before starting the app."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
