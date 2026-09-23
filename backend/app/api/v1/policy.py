from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.policies.packages import PolicyPackageRead, list_packages, resolve_package
from app.probing.catalog import probe_manifest

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get("/probes")
async def get_probe_catalog() -> list[dict]:
    """Catálogo de classes de probe M6 disponíveis (para escolher o allowlist)."""
    return probe_manifest()


@router.get("/packages", response_model=list[PolicyPackageRead])
async def get_policy_packages() -> list[PolicyPackageRead]:
    """Pacotes de política disponíveis (M10-P0), já resolvidos contra os catálogos."""
    return list_packages()


@router.get("/packages/{package_id}", response_model=PolicyPackageRead)
async def get_policy_package(package_id: str) -> PolicyPackageRead:
    try:
        return resolve_package(package_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy package not found"
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
