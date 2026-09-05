from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from app.scanning.spec import FormField, HtmlForm

_SECURITY_HEADERS = {
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
}


class _HtmlPageParser(HTMLParser):
    """Collects links, forms, tech markers and meta from an HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.forms: list[HtmlForm] = []
        self.meta: dict[str, str] = {}
        self.scripts: list[str] = []
        self._current_form: HtmlForm | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("a", "link"):
            href = attr_map.get("href")
            if (
                href
                and href.strip()
                and not href.strip().startswith(("#", "javascript:", "mailto:"))
            ):
                self.links.append(href.strip())
        elif tag == "script":
            src = attr_map.get("src")
            if src:
                self.scripts.append(src)
        elif tag == "form":
            self._current_form = HtmlForm(
                action=attr_map.get("action", ""),
                method=attr_map.get("method", "get").lower(),
            )
            self.forms.append(self._current_form)
        elif tag == "input" and self._current_form is not None:
            self._current_form.fields.append(
                FormField(
                    name=attr_map.get("name", ""),
                    type=attr_map.get("type", "text"),
                    value=attr_map.get("value"),
                )
            )
        elif tag == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").lower()
            content = attr_map.get("content")
            if name and content:
                self.meta[name] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current_form = None


def parse_html(url: str, body: str) -> dict[str, Any]:
    """Parse an HTML body into links/forms/scripts/meta with absolute URLs."""
    parser = _HtmlPageParser()
    try:
        parser.feed(body)
    except Exception:  # noqa: BLE001 — malformed markup must not abort the scan
        return {"links": [], "forms": [], "scripts": [], "meta": {}}

    def _absolute(target: str) -> str:
        try:
            return urljoin(url, target)
        except ValueError:
            return target

    links = [
        link
        for link in (_absolute(item) for item in parser.links)
        if _is_same_host(url, link)
    ]
    return {
        "links": links,
        "forms": parser.forms,
        "scripts": [_absolute(s) for s in parser.scripts],
        "meta": dict(parser.meta),
    }


def _is_same_host(base: str, candidate: str) -> bool:
    """Keep only links that resolve back to the target host (no external crawl)."""
    return urlparse(candidate).netloc == urlparse(base).netloc


_COOKIE_ATTRIBUTES = {
    "samesite",
    "max-age",
    "domain",
    "path",
    "secure",
    "httponly",
    "priority",
    "expires",
    "partitioned",
    "partitions",
}


def _parse_set_cookies(value: str) -> list[dict[str, Any]]:
    """Parse joined ``Set-Cookie`` values into per-cookie attribute dicts.

    ``_headers_to_dict`` joins multi-valued headers with ``; ``; re-splitting
    on ``;`` then grouping is unambiguous because cookie attributes are a
    closed set — anything else with ``key=value`` starts the next cookie.
    """
    tokens = [t.strip() for t in (value or "").split(";") if t.strip()]
    cookies: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for token in tokens:
        key, _, val = token.partition("=")
        key_lower = key.lower()
        if current is None:
            current = {
                "name": key,
                "flags": [],
                "secure": False,
                "httponly": False,
                "samesite": None,
            }
            cookies.append(current)
        elif key_lower in _COOKIE_ATTRIBUTES:
            current["flags"].append(token.lower())
            if key_lower == "secure":
                current["secure"] = True
            elif key_lower == "httponly":
                current["httponly"] = True
            elif key_lower == "samesite":
                current["samesite"] = val.lower()
        else:
            current = {
                "name": key,
                "flags": [],
                "secure": False,
                "httponly": False,
                "samesite": None,
            }
            cookies.append(current)
    return cookies


def analyze_headers(headers: dict[str, str]) -> dict[str, Any]:
    """Turn raw response headers into security-relevant observations."""
    lower = {k.lower(): v for k, v in headers.items()}
    present = sorted(set(_SECURITY_HEADERS) & set(lower))
    missing = sorted(_SECURITY_HEADERS - set(lower))

    cookies = _parse_set_cookies(lower.get("set-cookie", ""))

    return {
        "security_headers_present": present,
        "security_headers_missing": missing,
        "server": lower.get("server"),
        "x_powered_by": lower.get("x-powered-by"),
        "content_type": lower.get("content-type"),
        "cookies": cookies,
        "cors_allow_origin": lower.get("access-control-allow-origin"),
        "csp": lower.get("content-security-policy"),
    }