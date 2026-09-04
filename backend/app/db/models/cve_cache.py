from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CveCache(Base):
    """Cached CVE lookups (external source) with TTL for Etapa 9."""

    __tablename__ = "cve_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cve_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=True)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ttl: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
