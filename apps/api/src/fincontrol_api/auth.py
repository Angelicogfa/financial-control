"""Single-user authentication: Argon2 password hash and JWT session cookie (item 9.5).

The credential lives in the unversioned `.env` (AUTH_USERNAME, AUTH_PASSWORD_HASH,
AUTH_JWT_SECRET). The API issues an HS256 JWT in an httpOnly, SameSite=Strict cookie; a
`Authorization: Bearer` header is accepted too for scripts.

CLI helpers:
    python -m fincontrol_api.auth hash-password   # prompts twice, prints the .env line
    python -m fincontrol_api.auth new-secret      # prints a random AUTH_JWT_SECRET line
"""

from __future__ import annotations

import getpass
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fincontrol_config import Settings
from fincontrol_core.errors import DomainError

SESSION_COOKIE = "fincontrol_session"
JWT_ALGORITHM = "HS256"

_hasher = PasswordHasher()


class AuthenticationError(DomainError):
    """Missing, invalid or expired credentials (HTTP 401)."""

    code = "UNAUTHENTICATED"


class AuthNotConfiguredError(DomainError):
    """AUTH_PASSWORD_HASH / AUTH_JWT_SECRET were not set in .env (HTTP 503)."""

    code = "AUTH_NOT_CONFIGURED"


@dataclass(frozen=True)
class Session:
    username: str
    token: str
    expires_at: datetime


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _require_configured(settings: Settings) -> None:
    if not settings.auth_configured:
        raise AuthNotConfiguredError(
            "Authentication is not configured: set AUTH_PASSWORD_HASH and AUTH_JWT_SECRET in .env"
        )


def login(settings: Settings, username: str, password: str) -> Session:
    """Validate the single-user credential and issue a signed session token."""
    _require_configured(settings)
    assert settings.auth_password_hash is not None and settings.auth_jwt_secret is not None
    valid_user = secrets.compare_digest(username, settings.auth_username)
    valid_password = verify_password(settings.auth_password_hash, password)
    if not (valid_user and valid_password):
        raise AuthenticationError("Invalid username or password")
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.auth_token_ttl_minutes)
    token = jwt.encode(
        {"sub": settings.auth_username, "exp": expires_at, "iat": datetime.now(UTC)},
        settings.auth_jwt_secret,
        algorithm=JWT_ALGORITHM,
    )
    return Session(settings.auth_username, token, expires_at)


def authenticate(settings: Settings, token: str | None) -> str:
    """Return the username of a valid session token or raise AuthenticationError."""
    _require_configured(settings)
    assert settings.auth_jwt_secret is not None
    if not token:
        raise AuthenticationError("Authentication required")
    try:
        claims = jwt.decode(token, settings.auth_jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as err:
        raise AuthenticationError("Session expired") from err
    except jwt.InvalidTokenError as err:
        raise AuthenticationError("Invalid session") from err
    if claims.get("sub") != settings.auth_username:
        raise AuthenticationError("Invalid session")
    return str(claims["sub"])


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else ""
    if command == "hash-password":
        first = getpass.getpass("New password: ")
        if len(first) < 10:
            print("Use at least 10 characters.", file=sys.stderr)
            return 1
        if getpass.getpass("Repeat password: ") != first:
            print("Passwords do not match.", file=sys.stderr)
            return 1
        # Single quotes keep Docker Compose and python-dotenv from expanding the "$" signs.
        print(f"AUTH_PASSWORD_HASH='{hash_password(first)}'")
        return 0
    if command == "new-secret":
        print(f"AUTH_JWT_SECRET={secrets.token_hex(32)}")
        return 0
    print("usage: python -m fincontrol_api.auth [hash-password|new-secret]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
