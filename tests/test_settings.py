import pytest

from config.settings import Settings, validate_runtime_settings


@pytest.mark.parametrize(
    "secret",
    ["", "too-short", "replace_with_at_least_32_random_bytes"],
)
def test_runtime_configuration_rejects_unsafe_jwt_secrets(secret):
    settings = Settings(_env_file=None, jwt_secret_key=secret)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be configured") as error:
        validate_runtime_settings(settings)

    if secret:
        assert secret not in str(error.value)


def test_runtime_configuration_accepts_long_random_jwt_secret():
    settings = Settings(
        _env_file=None,
        jwt_secret_key="test-only-random-signing-key-material-0123456789",
    )

    validate_runtime_settings(settings)


def test_production_requires_shared_rate_limit_storage():
    settings = Settings(
        _env_file=None,
        environment="production",
        jwt_secret_key="test-only-random-signing-key-material-0123456789",
        rate_limit_redis_url=None,
    )
    with pytest.raises(RuntimeError, match="RATE_LIMIT_REDIS_URL is required"):
        validate_runtime_settings(settings)


def test_production_accepts_redis_shared_rate_limit_configuration():
    settings = Settings(
        _env_file=None,
        environment="production",
        jwt_secret_key="test-only-random-signing-key-material-0123456789",
        rate_limit_redis_url="rediss://redis.example.invalid/0",
    )
    validate_runtime_settings(settings)


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("access_token_expire_minutes", 0, "ACCESS_TOKEN_EXPIRE_MINUTES"),
        ("access_token_expire_minutes", 1441, "ACCESS_TOKEN_EXPIRE_MINUTES"),
        ("rate_limit_requests", 0, "Rate limit requests"),
        ("rate_limit_window_seconds", 0, "Rate limit requests"),
        ("max_request_body_bytes", 0, "MAX_REQUEST_BODY_BYTES"),
    ],
)
def test_runtime_configuration_rejects_invalid_limits(setting, value, message):
    settings = Settings(
        _env_file=None,
        jwt_secret_key="test-only-random-signing-key-material-0123456789",
        **{setting: value},
    )

    with pytest.raises(RuntimeError, match=message):
        validate_runtime_settings(settings)
