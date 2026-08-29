from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.session import verify_session_token
from app.db.session import get_db

DBSession = Annotated[AsyncSession, Depends(get_db)]


def require_auth(argus_session: str | None = Cookie(default=None)) -> None:
    """Guard for protected routers.

    When ``UI_PASSWORD`` is unset the API runs in open/dev mode and the guard
    is a no-op, so local development and tests don't need credentials.
    """
    settings = get_settings()
    if not settings.ui_password:
        return
    if not verify_session_token(argus_session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária",
        )

