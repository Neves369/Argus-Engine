from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from app.db.models.cve_cache import CveCache
from app.db.models.external_data_cache import ExternalDataCache
from app.db.session import async_session_factory
from app.sources.registry import DataSourceRegistry
from app.sources.spec import DataSourceSpec, SourceKind

logger = logging.getLogger(__name__)


class DataSourceError(RuntimeError):
    """Raised when a data source cannot be queried or is blocked."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC for TTL arithmetic."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _default_key(source: DataSourceSpec, params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


def _minimize(source: DataSourceSpec, data: Any) -> dict[str, Any]:
    """Keep only the fields the operator declared necessary (data minimization)."""
    if not source.fields:
        return {"response": data} if not isinstance(data, dict) else data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in source.fields}
    if isinstance(data, list):
        kept: list[Any] = []
        for item in data:
            if isinstance(item, dict):
                kept.append({k: v for k, v in item.items() if k in source.fields})
            else:
                kept.append(item)
        return {"items": kept}
    return {"response": data}


class DataSourceService:
    """Queries external data sources with rate limiting, normalization and caching.

    When a source is not configured or the network call fails, a deterministic
    simulated response is returned so the system degrades gracefully offline.
    """

    def __init__(self, registry: DataSourceRegistry) -> None:
        self._registry = registry
        self._last_invocation: dict[str, float] = {}

    def available_sources(self) -> list[str]:
        """Names of every configured source (agents query by role, not by name)."""
        return self._registry.available_sources()

    def _check_rate_limit(self, source: DataSourceSpec) -> None:
        if source.rate_limit <= 0:
            return
        last = self._last_invocation.get(source.name)
        now = time.monotonic()
        if last is not None and (now - last) < (1.0 / source.rate_limit):
            raise DataSourceError(f"Rate limit exceeded for source {source.name}")
        self._last_invocation[source.name] = now

    async def query(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if not self._registry.has_source(name):
            return self._simulated(name, params, reason="source-not-configured")

        source = self._registry.get_source(name)
        self._check_rate_limit(source)
        now = _utcnow()

        cached = await self._read_cache(source, params, now)
        if cached is not None:
            return cached

        try:
            raw = await self._fetch(source, params)
        except DataSourceError as exc:
            logger.warning("source fetch failed", extra={"source": name, "reason": str(exc)})
            return self._simulated(name, params, reason="fetch-error")

        minimized = _minimize(source, raw)
        result = {
            "status": "ok",
            "source": source.name,
            "data": minimized,
            "fetched_at": now.isoformat(),
        }
        await self._write_cache(source, params, minimized, now)
        return result

    async def _fetch(self, source: DataSourceSpec, params: dict[str, Any]) -> Any:
        if not source.url:
            raise DataSourceError(f"Source {source.name} has no URL configured")
        merged = {**source.params_template, **params}
        try:
            async with httpx.AsyncClient(timeout=source.timeout) as client:
                if source.method.upper() == "POST":
                    response = await client.post(source.url, json=merged)
                else:
                    response = await client.get(source.url, params=merged)
        except httpx.HTTPError as exc:
            raise DataSourceError(f"Source {source.name} request failed: {exc}") from exc

        if response.status_code >= 400:
            raise DataSourceError(
                f"Source {source.name} returned {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError:
            return {"response": response.text}

    async def _read_cache(
        self, source: DataSourceSpec, params: dict[str, Any], now: datetime
    ) -> dict[str, Any] | None:
        async with async_session_factory() as session:
            if source.kind == SourceKind.CVE:
                cve_id = str(params.get("id", _default_key(source, params)))
                row = (
                    await session.execute(
                        select(CveCache).where(CveCache.cve_id == cve_id)
                    )
                ).scalar_one_or_none()
                if row is None:
                    return None
                if now - _as_utc(row.cached_at) < timedelta(seconds=row.ttl):
                    return {
                        "status": "cache",
                        "source": source.name,
                        "data": row.data,
                        "fetched_at": row.cached_at.isoformat(),
                    }
                return None
            key = _default_key(source, params)
            row = (
                await session.execute(
                    select(ExternalDataCache).where(
                        ExternalDataCache.source == source.name,
                        ExternalDataCache.key == key,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if now - _as_utc(row.fetched_at) < timedelta(seconds=source.ttl):
                return {
                    "status": "cache",
                    "source": source.name,
                    "data": row.data,
                    "fetched_at": row.fetched_at.isoformat(),
                }
            return None

    async def _write_cache(
        self,
        source: DataSourceSpec,
        params: dict[str, Any],
        data: dict[str, Any],
        now: datetime,
    ) -> None:
        async with async_session_factory() as session:
            if source.kind == SourceKind.CVE:
                cve_id = str(params.get("id", _default_key(source, params)))
                session.add(CveCache(cve_id=cve_id, data=data, cached_at=now, ttl=source.ttl))
            else:
                session.add(
                    ExternalDataCache(
                        source=source.name,
                        key=_default_key(source, params),
                        data=data,
                        fetched_at=now,
                    )
                )
            await session.commit()

    def _simulated(
        self, name: str, params: dict[str, Any], *, reason: str
    ) -> dict[str, Any]:
        return {
            "status": "simulated",
            "source": name,
            "reason": reason,
            "data": {
                "note": "Source unavailable; returning deterministic simulated data.",
                "requested": params,
            },
            "fetched_at": _utcnow().isoformat(),
        }


def build_sources_service() -> DataSourceService:
    """Instantiate the service from the operator-declared manifest (settings)."""
    from app.core.config import get_settings

    registry = DataSourceRegistry(get_settings().sources_manifest)
    return DataSourceService(registry)
