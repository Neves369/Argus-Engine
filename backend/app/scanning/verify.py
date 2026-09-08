"""Live non-destructive verification probes for the Chariot (Etapa 15).

The safety check produces candidate findings from an already-observed scan;
the verification service re-probes the ``probe_url`` of scan-evidenced
candidates against the live target (a plain GET within the active-scanning
controls) and re-runs the page detectors on the fresh response to confirm or
refute each candidate.

Everything here is evidence-grounded and auditable: a probe records the real
status code, final URL and observed headers; a block (kill-switch, out of
scope, robots disallow, unreachable host) is recorded as ``skipped``, never
fabricated. Findings with no probeable URL (e.g. purely source-derived) are
left unverified (``None``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from app.core.security import is_kill_switch_active, validate_scope
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.detectors import detect_on_page
from app.scanning.robots import RobotsRules
from app.scanning.service import ScanReport

logger = logging.getLogger(__name__)

_VERIFY_HEADERS = (
    "server",
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "set-cookie",
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _probe_url(finding: dict[str, Any]) -> str | None:
    """The live URL a candidate finding can be re-probed against.

    Prefers the page URL stamped by ``derive_findings_from_scan``
    (``probe_url``); falls back to ``affected`` when it already looks like a
    URL, else derives an ``https://`` URL from the affected host. Findings
    without any of those (source-derived leads) have nothing to probe.
    """
    url = str(finding.get("probe_url") or "").strip()
    affected = str(finding.get("affected") or "").strip()
    if not url:
        url = affected
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}/"
    return url


class VerificationService:
    """Coordinates live non-destructive probes under the same controls as
    active scanning (scope, kill-switch, robots, rate limit, timeout, audit)."""

    def __init__(
        self,
        *,
        client: ScanHTTPClient | None = None,
        respect_robots: bool = True,
        max_probes: int = 10,
        enabled: bool = True,
    ) -> None:
        self._client = client or ScanHTTPClient()
        self._respect_robots = respect_robots
        self._max_probes = max(0, int(max_probes or 0))
        self._enabled = bool(enabled)
        self._robots_cache: dict[str, RobotsRules | None] = {}

    async def verify(
        self,
        *,
        report: ScanReport | None,
        findings: list[dict[str, Any]],
        target: dict[str, Any] | None = None,
    ) -> list[dict[str, Any] | None]:
        """Re-probe scan-evidenced findings; return one entry per input finding.

        The entry is ``None`` when the finding was not probed (no probeable
        URL, verification disabled, cap reached) and a dict when it was —
        ``{"confirmed": bool, "probe": {...}}`` — with the probe payload as
        live evidence. Order matches the input ``findings``.
        """
        if not self._enabled or self._max_probes <= 0:
            return [None] * len(findings)
        if not findings or report is None:
            return [None] * len(findings)

        target_name = str((target or {}).get("name") or "")
        try:
            validate_scope(target_name)
        except ValueError:
            return [None] * len(findings)
        if is_kill_switch_active():
            return [None] * len(findings)

        by_url: dict[str, list[int]] = {}
        urls: list[str] = []
        for idx, finding in enumerate(findings):
            url = _probe_url(finding)
            if url is None:
                continue
            by_url.setdefault(url, []).append(idx)
            if url not in urls:
                urls.append(url)

        if not urls:
            return [None] * len(findings)

        outcomes: list[dict[str, Any] | None] = [None] * len(findings)
        for url in urls[: self._max_probes]:
            probe = await self._probe(url)
            for idx in by_url[url]:
                title = str(findings[idx].get("title") or "")
                outcomes[idx] = {
                    "confirmed": title in probe["titles_confirmed"],
                    "probe": {
                        key: probe[key]
                        for key in (
                            "url",
                            "status_code",
                            "final_url",
                            "headers",
                            "observed_at",
                            "skipped",
                            "skip_reason",
                        )
                    },
                }
        return outcomes

    async def _probe(self, url: str) -> dict[str, Any]:
        host = urlparse(url).netloc
        blocked = await self._robots_blocked(host, url)
        if blocked is not None:
            return self._probe_blocked(url, blocked)
        try:
            page = await self._client.get_page(url)
        except ScanError as exc:  # noqa: BLE001 - HTTPS down: fall back to http
            fallback = url.replace("https://", "http://", 1)
            if fallback == url:
                return self._probe_blocked(url, f"unreachable: {exc}")
            try:
                page = await self._client.get_page(fallback)
            except ScanError as exc2:  # noqa: BLE001 - transcribed as skipped
                return self._probe_blocked(url, f"unreachable: {exc2}")
            url = fallback

        fresh_titles = {f["title"] for f in detect_on_page(page)}
        return {
            "url": url,
            "status_code": page.status_code,
            "final_url": page.final_url,
            "headers": {
                key: value
                for key, value in page.headers.items()
                if key in _VERIFY_HEADERS
            },
            "titles_confirmed": sorted(fresh_titles),
            "observed_at": _utcnow(),
            "skipped": False,
            "skip_reason": None,
        }

    def _probe_blocked(self, url: str, reason: str) -> dict[str, Any]:
        return {
            "url": url,
            "status_code": None,
            "final_url": None,
            "headers": {},
            "titles_confirmed": [],
            "observed_at": _utcnow(),
            "skipped": True,
            "skip_reason": reason,
        }

    async def _robots_blocked(self, host: str, url: str) -> str | None:
        """Robots check for a single probe, cached per host.

        A probe path disallowed by robots is never sent — recorded as a
        skipped probe (self-imposed restriction, same as the crawl).
        """
        if not self._respect_robots:
            return None
        rules = self._robots_cache.get(host, _MISSING)
        if rules is _MISSING:
            rules = await self._load_robots(host)
            self._robots_cache[host] = rules
        if rules is None:
            return None
        path = urlparse(url).path or "/"
        if rules.is_allowed(path):
            return None
        return "robots disallow"

    async def _load_robots(self, host: str) -> RobotsRules | None:
        # robots.txt is a single small fetch; cache per host.
        robots_url = urljoin(f"https://{host}/", "robots.txt")
        try:
            page = await self._client.fetch_no_rate_limit(robots_url)
        except ScanError:
            return None
        if page.status_code not in (200, 204):
            return None
        return RobotsRules.parse(page.body, user_agent=self._client.user_agent)


_MISSING = object()


def build_verification_service() -> VerificationService:
    """Instantiate the verifier from settings (``CHARIOT_VERIFY_*`` +
    ``SCAN_*`` controls shared with the active scanner)."""
    from app.core.config import get_settings

    settings = get_settings()
    client = ScanHTTPClient(
        rate_limit=settings.scan_rate_limit,
        timeout=settings.scan_request_timeout,
        max_body_bytes=settings.scan_max_body_bytes,
        user_agent=settings.scan_user_agent,
        extra_headers=settings.scan_extra_headers,
        cookies=settings.scan_cookies,
    )
    return VerificationService(
        client=client,
        respect_robots=settings.scan_respect_robots,
        max_probes=settings.chariot_verify_max_probes,
        enabled=settings.chariot_verify_enabled,
    )