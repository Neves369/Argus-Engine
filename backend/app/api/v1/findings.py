from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.config import get_settings
from app.db.models import Evidence, Finding
from app.db.models.finding import ALLOWED_TRANSITIONS, FindingStatus
from app.schemas.evidence import EvidenceRead
from app.schemas.finding import FindingRead, FindingUpdate
from app.services.evidence import EvidenceStore
from app.services.false_positives import FalsePositiveBlacklist
from app.services.quality import QualityScorer, ValidationOutcome, ValidationPipeline

router = APIRouter(prefix="/findings", tags=["findings"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


@router.get("/{finding_id}", response_model=FindingRead)
async def get_finding(finding_id: int, db: DBSession) -> Finding:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding


@router.patch("/{finding_id}", response_model=FindingRead)
async def update_finding(finding_id: int, payload: FindingUpdate, db: DBSession) -> Finding:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")

    current = FindingStatus(finding.status)
    if payload.status not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition {current.value} -> {payload.status.value}",
        )

    finding.status = payload.status.value
    await db.commit()
    await db.refresh(finding)
    return finding


@router.post("/{finding_id}/validate", response_model=FindingRead)
async def validate_finding(finding_id: int, db: DBSession) -> Finding:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")

    if finding.status != FindingStatus.CANDIDATE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot validate a finding in state {finding.status}",
        )

    evidence_count = (
        await db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.finding_id == finding_id)
        )
        or 0
    )

    settings = get_settings()
    scorer = QualityScorer()
    pipeline = ValidationPipeline(
        scorer,
        FalsePositiveBlacklist(settings.fp_blacklist),
        threshold=settings.quality_score_threshold,
    )

    outcome = pipeline.validate(finding, evidence_count)
    finding.score = scorer.score(finding, evidence_count)

    if outcome is ValidationOutcome.VALIDATE:
        finding.status = FindingStatus.VALIDATED.value
        finding.validated_at = _utcnow()
        finding.requires_human_review = False
    elif outcome is ValidationOutcome.FALSE_POSITIVE:
        finding.status = FindingStatus.FALSE_POSITIVE.value
        finding.requires_human_review = False
    else:
        finding.requires_human_review = True

    await db.commit()
    await db.refresh(finding)
    return finding


@router.post(
    "/{finding_id}/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def attach_evidence(finding_id: int, file: UploadFile, db: DBSession) -> Evidence:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")

    content = await file.read()
    evidence = await EvidenceStore().save(
        db,
        run_id=finding.run_id,
        finding_id=finding_id,
        file_name=file.filename or "evidence",
        content=content,
        mime=file.content_type,
    )
    await db.commit()
    await db.refresh(evidence)
    return evidence
