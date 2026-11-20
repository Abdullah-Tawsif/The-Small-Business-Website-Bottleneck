import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt

from config.settings import get_settings

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_SIZE = 16
KEY_LENGTH = 32
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "agencyforge"
JWT_AUDIENCE = "agencyforge-api"
ALLOWED_ROLES = {"admin", "staff"}


class SecurityError(Exception):
    """Base exception for security-related failures."""


class InvalidTokenError(SecurityError):
    """Raised when an access token is invalid or expired."""


class PasswordError(SecurityError):
    """Raised for invalid password input."""


def hash_password(password: str) -> str:
    """Return a salted scrypt hash suitable for storage."""
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise PasswordError("Password must be between 10 and 128 characters.")

    salt = secrets.token_bytes(SALT_SIZE)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_LENGTH,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password without revealing which part of the hash failed."""
    if not isinstance(password, str) or not isinstance(encoded_hash, str):
        return False
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded_hash.split("$")
        if algorithm != "scrypt":
            return False
        if (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        if len(salt) != SALT_SIZE or len(expected) != KEY_LENGTH:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=KEY_LENGTH,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _jwt_secret() -> str:
    secret = get_settings().jwt_secret_key
    if len(secret.encode("utf-8")) < 32:
        raise SecurityError("JWT_SECRET_KEY must be set to at least 32 bytes.")
    return secret


def create_access_token(
    user_id: int,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    """Create a short-lived signed JWT. Secret is read from environment settings."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise SecurityError("Invalid user ID.")
    if role not in ALLOWED_ROLES:
        raise SecurityError("Invalid user role.")

    settings = get_settings()
    lifetime = (
        settings.access_token_expire_minutes
        if expires_minutes is None
        else expires_minutes
    )
    if (
        isinstance(lifetime, bool)
        or not isinstance(lifetime, int)
        or not 1 <= lifetime <= 1440
    ):
        raise SecurityError("Token lifetime must be between 1 and 1440 minutes.")

    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + lifetime * 60,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(claims, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature and standard claims before returning token claims."""
    if not isinstance(token, str) or not token:
        raise InvalidTokenError("Invalid or expired access token.")

    try:
        claims = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "role", "iat", "exp", "iss", "aud", "jti"]},
        )
        subject = claims.get("sub", "")
        if not subject.isdigit() or int(subject) <= 0:
            raise InvalidTokenError("Invalid or expired access token.")
        if claims.get("role") not in ALLOWED_ROLES:
            raise InvalidTokenError("Invalid or expired access token.")
        return claims
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid or expired access token.") from exc
