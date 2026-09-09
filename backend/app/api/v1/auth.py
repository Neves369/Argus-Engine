from __future__ import annotations

import hmac
import logging
import time

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import DBSession, require_auth
from app.core.auth_overrides import effective_ui_password
from app.core.config import get_settings
from app.core.crypto import has_encryption
from app.core.session import COOKIE_NAME, create_session_token, verify_session_token
from app.services.app_settings import set_ui_password_override

logger = logging.getLogger("argus")

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_MAX_AGE = 28_800  # 8h


class LoginPayload(BaseModel):
    password: str


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=512)


# Rate-limit em memória por IP (single-process): janela deslizante de
# tentativas erradas. Zera no restart — ver app/core/config.py.
_login_attempts: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _reset_login_attempts() -> None:
    _login_attempts.clear()


def _prune(ip: str) -> int:
    window = get_settings().login_window_seconds
    cutoff = time.monotonic() - window
    attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    if attempts:
        _login_attempts[ip] = attempts
    else:
        _login_attempts.pop(ip, None)
    return len(attempts)


def _check_login_allowed(ip: str) -> None:
    attempts = _prune(ip)
    settings = get_settings()
    if attempts >= settings.login_max_attempts:
        first = _login_attempts[ip][0]
        retry_after = max(
            1, int(settings.login_window_seconds - (time.monotonic() - first))
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas tentativas de login. Tente novamente em {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


def _record_failed_login(ip: str) -> None:
    window = get_settings().login_window_seconds
    _login_attempts.setdefault(ip, []).append(time.monotonic())
    if len(_login_attempts[ip]) > window * 10:
        _prune(ip)


def _clear_login_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)


@router.post("/login")
async def login(payload: LoginPayload, request: Request) -> JSONResponse:
    ip = _client_ip(request)
    _check_login_allowed(ip)

    expected = effective_ui_password()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auth desabilitada (UI_PASSWORD não configurado)",
        )
    if not hmac.compare_digest(payload.password.encode("utf-8"), expected.encode("utf-8")):
        _record_failed_login(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha inválida")

    _clear_login_attempts(ip)
    token = create_session_token()
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=get_settings().session_cookie_secure,
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
    if not effective_ui_password():
        return {"authenticated": True, "ui_enabled": False}
    return {"authenticated": verify_session_token(argus_session), "ui_enabled": True}


@router.post("/password", dependencies=[Depends(require_auth)])
async def change_password(payload: PasswordChange, db: DBSession) -> dict:
    settings = get_settings()
    expected = effective_ui_password()
    if not expected:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Auth desabilitada")

    if not hmac.compare_digest(
        payload.current_password.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha atual inválida")

    min_len = settings.ui_password_min_length
    if len(payload.new_password) < min_len:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A nova senha deve ter pelo menos {min_len} caracteres",
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A nova senha deve ser diferente da atual",
        )
    if not has_encryption():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Configure ARGUS_ENCRYPTION_KEY para persistir a nova senha",
        )

    await set_ui_password_override(payload.new_password, db)
    sessions_invalidated = not bool(settings.session_secret)
    logger.warning(
        "Senha do operador rotacionada",
        extra={"sessions_invalidated": sessions_invalidated},
    )
    return {"ok": True, "sessions_invalidated": sessions_invalidated}