from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.db.models import Target
from app.schemas.target import TargetCreate, TargetRead

router = APIRouter(prefix="/targets", tags=["targets"])


@router.post("", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
async def create_target(payload: TargetCreate, db: DBSession) -> Target:
    target = Target(name=payload.name, url=payload.url, notes=payload.notes)
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return target


@router.get("", response_model=list[TargetRead])
async def list_targets(db: DBSession) -> list[Target]:
    result = await db.execute(select(Target).order_by(Target.id))
    return list(result.scalars().all())


@router.get("/{target_id}", response_model=TargetRead)
async def get_target(target_id: int, db: DBSession) -> Target:
    target = await db.get(Target, target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return target
