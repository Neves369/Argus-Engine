from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import (
    activate_kill_switch,
    is_kill_switch_active,
    kill_switch_source,
)

logger = logging.getLogger("argus")

router = APIRouter(prefix="/operate", tags=["operate"])


class KillSwitchActivate(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.get("/kill-switch")
async def kill_switch_status() -> dict:
    return {
        "active": is_kill_switch_active(),
        "source": kill_switch_source(),
    }


@router.post("/kill-switch")
async def activate_kill_switch_route(payload: KillSwitchActivate) -> dict:
    """Ativa o kill-switch em runtime (one-way / abort-only).

    Fail-closed: só pode ativar. Desativar exige remover `KILL_SWITCH` do
    ambiente e reiniciar o processo — um painel comprometido nunca consegue
    destravar a operação.
    """
    if is_kill_switch_active():
        if get_settings().kill_switch:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Kill-switch está ativo via KILL_SWITCH (env). "
                    "Para desativar, reinicie sem a variável."
                ),
            )
        return {"active": True, "source": "runtime"}

    activate_kill_switch()
    logger.warning("Kill-switch ativado em runtime", extra={"reason": payload.reason})
    return {"active": True, "source": "runtime"}