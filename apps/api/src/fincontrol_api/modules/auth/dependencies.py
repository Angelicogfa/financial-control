"""FastAPI dependency providers for the auth module.

Scope: single-user login session.
"""

from __future__ import annotations

from fastapi import Depends, Request
from fincontrol_config import get_settings

from fincontrol_api.core.config import AppSettings
from fincontrol_api.core.security import SESSION_COOKIE
from fincontrol_api.modules.auth.use_cases import AuthHandler


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
