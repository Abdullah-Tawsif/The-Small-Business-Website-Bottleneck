import pytest

from utils.security import (
    InvalidTokenError,
    PasswordError,
    SecurityError,
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
    with pytest.raises(SecurityError):
        create_access_token(user_id=7, role="superuser")


@pytest.mark.parametrize("lifetime", [0, -1, 1441, 1.5, True])
def test_rejects_invalid_explicit_token_lifetime(lifetime):
    with pytest.raises(SecurityError, match="Token lifetime"):
        create_access_token(user_id=7, role="staff", expires_minutes=lifetime)


@pytest.mark.parametrize("user_id", [0, -1, 1.5, True, "7"])
def test_rejects_invalid_user_identifiers(user_id):
    with pytest.raises(SecurityError, match="Invalid user ID"):
        create_access_token(user_id=user_id, role="staff")
