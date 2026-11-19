import pytest

from utils.security import (
    InvalidTokenError,
    PasswordError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-bytes-long")
    from config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_password_hash_and_verify():
    encoded = hash_password("CorrectHorseBatteryStaple!")
    assert encoded != "CorrectHorseBatteryStaple!"
    assert verify_password("CorrectHorseBatteryStaple!", encoded)
    assert not verify_password("incorrect-password", encoded)


def test_password_hash_is_salted():
    first = hash_password("CorrectHorseBatteryStaple!")
    second = hash_password("CorrectHorseBatteryStaple!")
    assert first != second


def test_rejects_short_password():
    with pytest.raises(PasswordError):
        hash_password("short")


def test_jwt_round_trip():
    token = create_access_token(user_id=7, role="admin")
    claims = decode_access_token(token)
    assert claims["sub"] == "7"
    assert claims["role"] == "admin"


def test_rejects_tampered_token():
    token = create_access_token(user_id=7, role="staff")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token + "tampered")


def test_rejects_invalid_role():
    with pytest.raises(Exception):
        create_access_token(user_id=7, role="superuser")
