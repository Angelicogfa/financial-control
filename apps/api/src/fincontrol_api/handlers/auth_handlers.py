"""Login, logout and session validation for the single configured user (item 9.5)."""

from __future__ import annotations

from fincontrol_config import Settings

from fincontrol_api import auth
from fincontrol_api.schemas import LoginRequest


class AuthHandler:
    """Application handler for the single-user session lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def login(self, req: LoginRequest) -> auth.Session:
        return auth.login(self.settings, req.username, req.password)

    def authenticate(self, token: str | None) -> str:
        return auth.authenticate(self.settings, token)

    @property
    def cookie_max_age_seconds(self) -> int:
        return self.settings.auth_token_ttl_minutes * 60

    @property
    def cookie_secure(self) -> bool:
        return self.settings.auth_cookie_secure
