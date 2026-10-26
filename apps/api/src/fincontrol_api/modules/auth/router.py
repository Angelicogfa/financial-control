"""HTTP controllers (routers) of the auth module; they only delegate to use cases.

Scope: single-user login session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from fincontrol_api.core.security import SESSION_COOKIE
from fincontrol_api.modules.auth.dependencies import get_auth_handler, require_user
from fincontrol_api.modules.auth.schemas import CurrentUserDTO, LoginRequest
from fincontrol_api.modules.auth.use_cases import AuthHandler

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login", response_model=CurrentUserDTO)
def login(
    payload: LoginRequest,
    response: Response,
    handler: AuthHandler = Depends(get_auth_handler),
) -> CurrentUserDTO:
    session = handler.login(payload)
    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=handler.cookie_max_age_seconds,
        httponly=True,
        secure=handler.cookie_secure,
        samesite="strict",
        path="/",
    )
    return CurrentUserDTO(username=session.username, expires_at=session.expires_at)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@auth_router.get("/me", response_model=CurrentUserDTO)
def me(username: str = Depends(require_user)) -> CurrentUserDTO:
    return CurrentUserDTO(username=username)
