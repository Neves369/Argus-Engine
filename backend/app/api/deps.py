from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_overrides import effective_ui_password
from app.core.session import verify_session_token
from app.db.session import get_db

DBSession = Annotated[AsyncSession, Depends(get_db)]


def require_auth(argus_session: str | None = Cookie(default=None)) -> None:
    """Guard for protected routers.

    When no effective ``UI_PASSWORD`` is set the API runs in open/dev mode and
    the guard is a no-op, so local development and tests don't need
    credentials.
    """
    if not effective_ui_password():
        return
    if not verify_session_token(argus_session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária",
        )

