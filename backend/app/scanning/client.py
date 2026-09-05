from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import httpx

from app.scanning.spec import TargetPage

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 8192


class ScanError(RuntimeError):
    """Raised when a request to the target fails or is blocked."""


def _headers_to_dict(headers: httpx.Headers) -> dict[str, str]:
    """Flatten response headers to ``{lowercase-name: joined-value}``.

    Multi-valued headers (e.g. multiple ``Set-Cookie``) are joined with ``; ``.
    """
    result: dict[str, str] = {}
    for key, value in headers.multi_items():
        lower = key.lower()
        if lower in result:
            result[lower] = f"{result[lower]}; {value}"
        else:
            result[lower] = value
    return result


class ScanHTTPClient:
    """HTTP client for active scanning with per-target rate limiting.

    Every request to the target is logged (structured), bounded by a timeout,
    capped in response size, and sent with redirect limits — the operational
    controls required for active scanning (see docs/adr/0006-active-scanning.md).
    """

    def __init__(
        self,
        *,
        rate_limit: float = 10.0,
        timeout: float = 10.0,
        max_body_bytes: int = 512_000,
        user_agent: str | None = None,
        max_redirects: int = 5,
        extra_headers: dict[str, str] | None = None,
        cookies: str | None = None,
    ) -> None:
        self._rate_limit = max(0.0, float(rate_limit))
        self._timeout = float(timeout)
        self._max_body_bytes = int(max_body_bytes)
        self.user_agent = user_agent or "ArgusEngine/0.1 (authorized scanning)"
        self._max_redirects = int(max_redirects)
        self._last_request: dict[str, float] = {}
        self._extra_headers = dict(extra_headers or {})
        self._cookies = cookies or ""
        self._jar: dict[str, str] = {}

    def _check_rate_limit(self, host: str) -> None:
        if self._rate_limit <= 0:
            return
        interval = 60.0 / self._rate_limit
        last = self._last_request.get(host)
        now = time.monotonic()
        if last is not None and (now - last) < interval:
            raise ScanError(f"Rate limit exceeded for target {host}")
        self._last_request[host] = now

    def _cookie_header(self, host: str) -> str:
        """Merge static (env) cookies with session cookies harvested from the
        target; dynamic session cookies win on name collisions."""
        merged: dict[str, str] = {}
        for raw in (self._cookies, self._jar.get(host, "")):
            for pair in raw.split("; "):
                if "=" in pair:
                    name, _, value = pair.partition("=")
                    merged[name] = value
        return "; ".join(f"{name}={value}" for name, value in merged.items())

    @staticmethod
    def _parse_set_cookie_pair(value: str) -> tuple[str, str] | None:
        pair = value.split(";", 1)[0].strip()
        if "=" not in pair:
            return None
        name, _, raw = pair.partition("=")
        return name, raw

    def _store_cookies(self, host: str, set_cookies: list[str]) -> None:
        """Harvest ``Set-Cookie`` values into the per-host session jar."""
        jar: dict[str, str] = {}
        for pair in self._jar.get(host, "").split("; "):
            if "=" in pair:
                name, _, value = pair.partition("=")
                jar[name] = value
        for value in set_cookies:
            parsed = self._parse_set_cookie_pair(value)
            if parsed is None:
                continue
            name, raw = parsed
            if raw == "" or "max-age=0" in value.lower():
                jar.pop(name, None)
            else:
                jar[name] = raw
        if jar:
            self._jar[host] = "; ".join(f"{name}={value}" for name, value in jar.items())
        else:
            self._jar.pop(host, None)

    async def get_page(self, url: str) -> TargetPage:
        """Fetch a single page, bounded and logged, returning structural signals."""
        return await self._send("GET", url)

    async def post_page(self, url: str, data: dict[str, str]) -> TargetPage:
        """Submit form-encoded data (used by dynamic login), bounded and logged."""
        return await self._send("POST", url, data=data)

    async def _send(
        self, method: str, url: str, *, data: dict[str, str] | None = None
    ) -> TargetPage:
        host = urlparse(url).netloc
        self._check_rate_limit(host)

        headers = {"User-Agent": self.user_agent, **self._extra_headers}
        cookie = self._cookie_header(host)
        if cookie:
            headers["Cookie"] = cookie

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=self._max_redirects,
            verify=True,
        ) as client:
            started = time.monotonic()
            try:
                async with client.stream(
                    method, url, headers=headers, data=data
                ) as response:
                    body = b""
                    truncated = False
                    async for chunk in response.aiter_bytes(_CHUNK_SIZE):
                        if len(body) + len(chunk) > self._max_body_bytes:
                            body += chunk[: max(0, self._max_body_bytes - len(body))]
                            truncated = True
                            break
                        body += chunk
                    set_cookies = list(response.headers.get_list("set-cookie"))
                    page = TargetPage(
                        url=str(response.url),
                        status_code=response.status_code,
                        headers=_headers_to_dict(response.headers),
                        body=body.decode(errors="replace"),
                        body_truncated=truncated,
                        final_url=str(response.url),
                    )
            except httpx.HTTPError as exc:
                logger.warning(
                    "scan request failed",
                    extra={"url": url, "host": host, "reason": str(exc)},
                )
                raise ScanError(f"Request to {url} failed: {exc}") from exc

        self._store_cookies(host, set_cookies)

        logger.info(
            "scan request",
            extra={
                "url": url,
                "host": host,
                "status": page.status_code,
                "bytes": len(page.body.encode("utf-8", errors="replace")),
                "truncated": page.body_truncated,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return page