"""FastAPI dependency providers for the auth module.

Scope: single-user login session.
"""

from __future__ import annotations

from fastapi import Depends, Request

from core.security import SESSION_COOKIE
from core.settings import AppSettings, get_settings
from domain.auth.services.use_cases import AuthHandler


def get_auth_handler(settings: AppSettings = Depends(get_settings)) -> AuthHandler:
    """Provide the AuthHandler instance."""
    return AuthHandler(settings=settings)


def require_user(
    request: Request,
    handler: AuthHandler = Depends(get_auth_handler),
) -> str:
    """Authenticate the request from the session cookie or a Bearer token."""
    token = request.cookies.get(SESSION_COOKIE)
    header = request.headers.get("Authorization", "")
    if not token and header.lower().startswith("bearer "):
        token = header[7:].strip()
    return handler.authenticate(token)
