from __future__ import annotations

import hmac

from fastapi import APIRouter, Cookie, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.session import COOKIE_NAME, create_session_token, verify_session_token

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_MAX_AGE = 28_800  # 8h


class LoginPayload(BaseModel):
    password: str


@router.post("/login")
async def login(payload: LoginPayload) -> JSONResponse:
    settings = get_settings()
    if not settings.ui_password:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auth desabilitada (UI_PASSWORD não configurado)",
        )
    if not hmac.compare_digest(payload.password, settings.ui_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha inválida")
    token = create_session_token()
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=SESSION_MAX_AGE,
    )
    return response


@router.post("/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me")
async def me(argus_session: str | None = Cookie(default=None)) -> dict[str, bool]:
    settings = get_settings()
    if not settings.ui_password:
        return {"authenticated": True}
    return {"authenticated": verify_session_token(argus_session)}
