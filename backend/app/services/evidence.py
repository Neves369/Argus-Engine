from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Evidence


class EvidenceStore:
    """Stores evidence files on disk and records metadata with a SHA-256 hash."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(get_settings().evidence_dir)

    @staticmethod
    def _content_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def save(
        self,
        db: AsyncSession,
        *,
        run_id: int | None,
        finding_id: int | None,
        file_name: str,
        content: bytes,
        mime: str | None = None,
    ) -> Evidence:
        digest = self._content_hash(content)
        run_dir = self.base_dir / (str(run_id) if run_id is not None else "unscoped")
        run_dir.mkdir(parents=True, exist_ok=True)

        stored_name = f"{digest}_{file_name}"
        path = run_dir / stored_name
        path.write_bytes(content)

        evidence = Evidence(
            finding_id=finding_id,
            run_id=run_id,
            file_name=file_name,
            file_path=str(path),
            sha256=digest,
            size=len(content),
            mime=mime,
        )
        db.add(evidence)
        await db.flush()
        return evidence
