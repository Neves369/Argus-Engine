"""Derive genuine, evidence-grounded findings from active-scan results.

Mirrors ``app/services/source_findings.py``: every finding produced here must
trace back to an actual observed response (status code, header, cookie flag,
form). Nothing is inferred, fabricated, or correlated to a CVE without a real
lookup — scan results are leads for a human operator, always
``status="candidate"`` and ``requires_human_review=True``.
"""

from __future__ import annotations

from typing import Any

from app.scanning.detectors import detect_on_page
from app.scanning.service import ScanReport


def derive_findings_from_scan(report: ScanReport) -> list[dict[str, Any]]:
    """Turn observed scan pages into candidate findings, deduped by title."""
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in report.pages:
        for finding in detect_on_page(page):
            if finding["title"] in seen:
                continue
            seen.add(finding["title"])
            findings.append(finding)
    return findings