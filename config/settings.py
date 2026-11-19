from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized environment-backed application settings."""

    app_name: str = "AgencyForge"
    environment: str = "development"
    jwt_secret_key: str = ""
    access_token_expire_minutes: int = 30
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
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
