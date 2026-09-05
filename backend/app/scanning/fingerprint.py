from __future__ import annotations

from app.scanning.spec import TargetPage

_MARKERS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "WordPress": (
        ("header", ("x-powered-by",)),
        ("body", ("wp-content",)),
        ("body", ("wp-includes",)),
    ),
    "PHP": (("body", (".php",)), ("header", ("x-powered-by",))),
    "Django": (("header", ("x-frame-options",)), ("body", ("csrfmiddlewaretoken",))),
    "Nginx": (("header", ("server",)),),
    "React": (("body", ("_next/static",)), ("body", ("react",))),
    "Next.js": (("body", ("_next/static",)),),
}


def fingerprint(page: TargetPage) -> list[str]:
    """Identify technology hints from headers and body without guessing.

    Only markers corroborated by an observed header value or literal body
    fragment are reported — never a version number inferred from nothing.
    """
    lower_headers = {k.lower(): v.lower() for k, v in page.headers.items()}
    body_lower = page.body.lower()
    detected: list[str] = []
    for tech, checks in _MARKERS.items():
        found = False
        for kind, needles in checks:
            if kind == "header":
                values = " ".join(lower_headers.values())
                found = any(needle in values for needle in needles)
            else:
                found = any(needle in body_lower for needle in needles)
            if found:
                break
        if found:
            detected.append(tech)
    return sorted(detected)


def server_version_banner(page: TargetPage) -> str | None:
    """Exact version banner (e.g. ``Apache/2.4.49``) when the server reveals it."""
    server = (page.headers.get("server") or "").strip()
    if not server:
        return None
    return server if any(c.isdigit() for c in server) else None