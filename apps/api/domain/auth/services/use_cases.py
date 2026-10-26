"""Use cases (command/query handlers) for the auth module.

Scope: single-user login session.
"""

from __future__ import annotations

from controllers.auth.requests import LoginRequest
from core import security
from core.settings import Settings


class AuthHandler:
    """Application handler for the single-user session lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def login(self, req: LoginRequest) -> security.Session:
        return security.login(self.settings, req.username, req.password)

    def authenticate(self, token: str | None) -> str:
        return security.authenticate(self.settings, token)

    @property
    def cookie_max_age_seconds(self) -> int:
        return self.settings.auth_token_ttl_minutes * 60

    @property
    def cookie_secure(self) -> bool:
        return self.settings.auth_cookie_secure
