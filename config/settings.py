
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized environment-backed application settings."""

    app_name: str = "AgencyForge"
    environment: str = "development"

    jwt_secret_key: str = ""

    access_token_expire_minutes: int = 30
    access_token_cookie_name: str = "access_token"

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    rate_limit_redis_url: str | None = None
    max_request_body_bytes: int = 1_000_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_runtime_settings(settings: Settings | None = None) -> None:
    """Fail startup when token signing is not configured safely."""
    settings = settings or get_settings()
    secret = settings.jwt_secret_key
    if (
        len(secret.encode("utf-8")) < 32
        or secret == "replace_with_at_least_32_random_bytes"
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 bytes of random data."
        )
    if not 1 <= settings.access_token_expire_minutes <= 1440:
        raise RuntimeError(
            "ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440."
        )
    if settings.rate_limit_requests < 1 or settings.rate_limit_window_seconds < 1:
        raise RuntimeError(
            "Rate limit requests and window settings must be positive."
        )
    if settings.rate_limit_redis_url:
        if not settings.rate_limit_redis_url.startswith(("redis://", "rediss://")):
            raise RuntimeError("RATE_LIMIT_REDIS_URL must use redis:// or rediss://.")
    elif settings.environment.lower() == "production":
        raise RuntimeError(
            "RATE_LIMIT_REDIS_URL is required in production for shared rate limits."
        )
    if settings.max_request_body_bytes < 1:
        raise RuntimeError("MAX_REQUEST_BODY_BYTES must be positive.")
