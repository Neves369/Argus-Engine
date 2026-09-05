from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.config import get_settings
from app.db.models import Evidence, Finding, FpRule
from app.db.models.finding import ALLOWED_TRANSITIONS, FindingStatus
from app.schemas.evidence import EvidenceRead
from app.schemas.finding import FindingRead, FindingUpdate
from app.schemas.fp_rule import FpRuleCreate, FpRuleRead, FpRuleUpdate
from app.services.evidence import EvidenceStore
from app.services.false_positives import FalsePositiveBlacklist
from app.services.fp_rules import FpRuleStore
from app.services.judge import LLMJudge
from app.services.quality import QualityScorer, ValidationOutcome, ValidationPipeline

router = APIRouter(prefix="/findings", tags=["findings"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


@router.get("/fp-rules", response_model=list[FpRuleRead])
async def list_fp_rules(db: DBSession) -> list[FpRule]:
    return list(await FpRuleStore().list_rules(db))


@router.post("/fp-rules", response_model=FpRuleRead, status_code=status.HTTP_201_CREATED)
async def create_fp_rule(payload: FpRuleCreate, db: DBSession) -> FpRule:
    rule = await FpRuleStore().create_rule(db, payload.pattern)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/fp-rules/{rule_id}", response_model=FpRuleRead)
async def toggle_fp_rule(rule_id: int, payload: FpRuleUpdate, db: DBSession) -> FpRule:
    rule = await FpRuleStore().set_enabled(db, rule_id, payload.enabled)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/fp-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fp_rule(rule_id: int, db: DBSession) -> None:
    deleted = await FpRuleStore().delete_rule(db, rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    await db.commit()


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
    if FindingStatus(payload.status) is FindingStatus.FALSE_POSITIVE:
        await FpRuleStore().learn_from_finding(db, finding)
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
    store = FpRuleStore()
    learned_patterns = await store.enabled_patterns(db)
    pipeline = ValidationPipeline(
        scorer,
        FalsePositiveBlacklist([*settings.fp_blacklist, *learned_patterns]),
        threshold=settings.quality_score_threshold,
        judge=LLMJudge(),
    )

    outcome, verdict = await pipeline.validate_with_judge(finding, evidence_count)
    finding.score = scorer.score(finding, evidence_count)

    if verdict is not None:
        meta = dict(finding.meta or {})
        meta["judge"] = {
            "outcome": verdict.outcome.value,
            "reason": verdict.reason,
            "tokens": verdict.tokens,
            "cost": verdict.cost,
            "model": verdict.model,
            "provider": verdict.provider,
        }
        finding.meta = meta

    if outcome is ValidationOutcome.FALSE_POSITIVE:
        await store.count_hits(db, finding)
        finding.status = FindingStatus.FALSE_POSITIVE.value
        finding.requires_human_review = False
    elif outcome is ValidationOutcome.VALIDATE:
        finding.status = FindingStatus.VALIDATED.value
        finding.validated_at = _utcnow()
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
