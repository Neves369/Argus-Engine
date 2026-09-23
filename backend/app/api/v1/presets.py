from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.policies.presets import PresetRead, list_presets, resolve_preset

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("", response_model=list[PresetRead])
async def get_presets() -> list[PresetRead]:
    """Presets Tarot disponíveis (M10-P3): composições prontas de cartas."""
    return list_presets()


@router.get("/{preset_id}", response_model=PresetRead)
async def get_preset(preset_id: str) -> PresetRead:
    try:
        return resolve_preset(preset_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found"
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
