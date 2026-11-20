
from functools import lru_cache
import re

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Centralized environment-backed application settings."""

    app_name: str = "AgencyForge"
    environment: str = "development"
    database_url: str | None = None

    jwt_secret_key: str = ""

    access_token_expire_minutes: int = 30
    access_token_cookie_name: str = "access_token"

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    rate_limit_redis_url: str | None = None
    auth_rate_limit_requests: int = 12
    public_write_rate_limit_requests: int = 12
    ai_rate_limit_requests: int = 6
    api_rate_limit_requests: int = 120
    admin_rate_limit_requests: int = 90
    readiness_rate_limit_requests: int = 10
    trusted_proxy_cidrs: str = ""
    ai_account_daily_limit: int = 60
    ai_session_daily_limit: int = 20
    ai_global_daily_limit: int = 1000
    ai_budget_namespace: str = "agencyforge"
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
    if settings.environment.lower() == "production":
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required in production.")
        try:
            database_url = make_url(settings.database_url)
        except (TypeError, ValueError, ArgumentError) as exc:
            raise RuntimeError("DATABASE_URL is invalid.") from exc
        if database_url.get_backend_name() == "sqlite":
            raise RuntimeError("DATABASE_URL must use PostgreSQL in production.")
        if database_url.get_backend_name() != "postgresql":
            raise RuntimeError("DATABASE_URL must use PostgreSQL in production.")
        if database_url.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise RuntimeError(
                "DATABASE_URL must use the configured PostgreSQL psycopg driver."
            )
        if not database_url.database or not database_url.host:
            raise RuntimeError(
                "DATABASE_URL must include a PostgreSQL host and database."
            )
    elif settings.database_url:
        try:
            make_url(settings.database_url)
        except (TypeError, ValueError, ArgumentError) as exc:
            raise RuntimeError("DATABASE_URL is invalid.") from exc
    if not 1 <= settings.access_token_expire_minutes <= 1440:
        raise RuntimeError(
            "ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440."
        )
    if settings.rate_limit_window_seconds < 1 or any(
        value < 1
        for value in (
            settings.rate_limit_requests,
            settings.auth_rate_limit_requests,
            settings.public_write_rate_limit_requests,
            settings.ai_rate_limit_requests,
            settings.api_rate_limit_requests,
            settings.admin_rate_limit_requests,
            settings.readiness_rate_limit_requests,
            settings.ai_account_daily_limit,
            settings.ai_session_daily_limit,
            settings.ai_global_daily_limit,
        )
    ):
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
    if not re.fullmatch(r"[A-Za-z0-9:_-]{1,40}", settings.ai_budget_namespace):
        raise RuntimeError("AI_BUDGET_NAMESPACE contains unsupported characters.")
